import json
from typing import Any, Dict, List, Optional, Set

from ..common import NEGATIVE_PROMPT_KEYWORDS_REGEX, clean_numeric_or_string, try_parse_json
from .base import AIMetadataBackend

class ComfyUIBackend(AIMetadataBackend):
    name = "ComfyUI"

    def detect(self, raw_meta: Dict[str, Any]) -> bool:
        for key in ("prompt", "workflow"):
            val = raw_meta.get(key)
            if isinstance(val, (dict, list)):
                return True
            parsed = try_parse_json(val)
            if isinstance(parsed, (dict, list)):
                return True
        return False

    def parse(self, raw_meta: Dict[str, Any]) -> Dict[str, Any]:
        include_workflow = "workflow" not in raw_meta

        for key in ("prompt", "workflow"):
            val = raw_meta.get(key)
            parsed = try_parse_json(val) if isinstance(val, str) else val
            if isinstance(parsed, (dict, list)):
                res = parse_comfyui_graph(parsed, include_workflow=include_workflow)
                if res.get("prompt") or res.get("seed") or res.get("model"):
                    return res
        return {}

def parse_comfyui_graph(graph_or_workflow: Any, include_workflow: bool = True) -> Dict[str, Any]:
    """Parse ComfyUI prompt API graph or visual LiteGraph workflow."""
    data: Dict[str, Any] = {"software": "ComfyUI"}
    if not graph_or_workflow:
        return data

    parsed = graph_or_workflow
    if isinstance(graph_or_workflow, str):
        try:
            parsed = json.loads(graph_or_workflow)
        except Exception:
            return data

    if not isinstance(parsed, dict):
        return data

    if "nodes" in parsed and isinstance(parsed["nodes"], list):
        return _parse_comfyui_litegraph(parsed, include_workflow=include_workflow)

    nodes = {str(k): v for k, v in parsed.items() if isinstance(v, dict) and "class_type" in v}
    if not nodes:
        return data

    # 1. Identify samplers and output nodes
    sampler_nodes = []
    output_nodes = []

    for nid, node in nodes.items():
        ctype = node.get("class_type", "")
        if any(s in ctype for s in ("KSampler", "SamplerCustom", "FluxSampler", "BasicGuider")):
            sampler_nodes.append((nid, node))
        if any(out in ctype for out in ("SaveImage", "PreviewImage", "VAEDecode")):
            output_nodes.append((nid, node))

    def trace_conditioning(node_ref: Any, visited: Optional[Set[str]] = None) -> List[str]:
        if visited is None:
            visited = set()
        if not node_ref or not isinstance(node_ref, (list, tuple)) or len(node_ref) < 1:
            return []

        target_id = str(node_ref[0])
        if target_id in visited or target_id not in nodes:
            return []
        visited.add(target_id)

        target_node = nodes[target_id]
        ctype = target_node.get("class_type", "")
        inputs = target_node.get("inputs", {})

        if "CLIPTextEncode" in ctype or ctype in ("ShowText", "CR Prompt Text", "easy prompt"):
            if "text_g" in inputs or "text_l" in inputs:
                parts = []
                tg = inputs.get("text_g")
                tl = inputs.get("text_l")
                if isinstance(tg, str) and tg.strip():
                    parts.append(tg.strip())
                if isinstance(tl, str) and tl.strip() and tl.strip() != tg.strip():
                    parts.append(tl.strip())
                return ["\n".join(parts)] if parts else []

            text = inputs.get("text")
            if isinstance(text, str) and text.strip():
                return [text.strip()]

        found = []
        for in_name, in_val in inputs.items():
            if any(term in in_name.lower() for term in ("conditioning", "positive", "negative", "guider")):
                found.extend(trace_conditioning(in_val, visited))
        return found

    # Sort/prioritize samplers: if multiple samplers exist, prefer the primary/base sampler
    # or resolve the one closest to output
    primary_sampler = None
    if sampler_nodes:
        # Check if one of them is the final sampler leading to VAEDecode
        if output_nodes:
            output_inputs = [str(inp[0]) for _, onode in output_nodes for inp in onode.get("inputs", {}).values() if isinstance(inp, (list, tuple)) and inp]
            for snid, snode in sampler_nodes:
                if snid in output_inputs:
                    primary_sampler = (snid, snode)
                    break
        if not primary_sampler:
            primary_sampler = sampler_nodes[0]

    positive_prompts: List[str] = []
    negative_prompts: List[str] = []

    # Process primary sampler first
    samplers_to_process = [primary_sampler] if primary_sampler else sampler_nodes

    for nid, node in samplers_to_process:
        inputs = node.get("inputs", {})

        if "positive" in inputs:
            positive_prompts.extend(trace_conditioning(inputs["positive"]))
        elif "guider" in inputs:
            positive_prompts.extend(trace_conditioning(inputs["guider"]))
        elif "conditioning" in inputs:
            positive_prompts.extend(trace_conditioning(inputs["conditioning"]))

        if "negative" in inputs:
            negative_prompts.extend(trace_conditioning(inputs["negative"]))

        if "seed" in inputs and "seed" not in data:
            data["seed"] = clean_numeric_or_string(str(inputs["seed"]))
        if "steps" in inputs and "steps" not in data:
            data["steps"] = clean_numeric_or_string(str(inputs["steps"]))
        if "cfg" in inputs and "cfg_scale" not in data:
            data["cfg_scale"] = clean_numeric_or_string(str(inputs["cfg"]))
        if "sampler_name" in inputs and "sampler" not in data:
            data["sampler"] = str(inputs["sampler_name"])
        if "scheduler" in inputs and "scheduler" not in data:
            data["scheduler"] = str(inputs["scheduler"])
        if "denoise" in inputs and "denoise" not in data:
            data["denoise"] = clean_numeric_or_string(str(inputs["denoise"]))

    # Scan checkpoints, loaders, samplers, schedulers
    for nid, node in nodes.items():
        ctype = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if ctype in ("CheckpointLoaderSimple", "CheckpointLoader") and "ckpt_name" in inputs:
            data["model"] = str(inputs["ckpt_name"])
        elif ctype == "UNETLoader" and "unet_name" in inputs:
            data["model"] = str(inputs["unet_name"])
        elif ctype == "VAELoader" and "vae_name" in inputs and "vae" not in data:
            data["vae"] = str(inputs["vae_name"])
        elif ctype == "KSamplerSelect" and "sampler_name" in inputs and "sampler" not in data:
            data["sampler"] = str(inputs["sampler_name"])
        elif ctype == "BasicScheduler":
            if "scheduler" in inputs and "scheduler" not in data:
                data["scheduler"] = str(inputs["scheduler"])
            if "steps" in inputs and "steps" not in data:
                data["steps"] = clean_numeric_or_string(str(inputs["steps"]))
            if "denoise" in inputs and "denoise" not in data:
                data["denoise"] = clean_numeric_or_string(str(inputs["denoise"]))
        elif ("RandomNoise" in ctype or "KSampler" in ctype) and "seed" not in data:
            if "noise_seed" in inputs:
                data["seed"] = clean_numeric_or_string(str(inputs["noise_seed"]))
            elif "seed" in inputs:
                data["seed"] = clean_numeric_or_string(str(inputs["seed"]))

        # Dimensions from EmptyLatentImage
        if "EmptyLatentImage" in ctype:
            if "width" in inputs and "width" not in data:
                data["width"] = clean_numeric_or_string(str(inputs["width"]))
            if "height" in inputs and "height" not in data:
                data["height"] = clean_numeric_or_string(str(inputs["height"]))

    # Fallback to direct CLIPTextEncode nodes if tracing yielded nothing
    if not positive_prompts:
        fallback_texts = []
        for nid, node in nodes.items():
            ctype = node.get("class_type", "")
            inputs = node.get("inputs", {})
            if "CLIPTextEncode" in ctype and "text" in inputs:
                t = inputs["text"]
                if isinstance(t, str) and t.strip():
                    fallback_texts.append(t.strip())

        if len(fallback_texts) == 1:
            positive_prompts.append(fallback_texts[0])
        elif len(fallback_texts) >= 2:
            neg_cands = [t for t in fallback_texts if NEGATIVE_PROMPT_KEYWORDS_REGEX.search(t)]
            pos_cands = [t for t in fallback_texts if not NEGATIVE_PROMPT_KEYWORDS_REGEX.search(t)]
            if pos_cands:
                positive_prompts.extend(pos_cands)
            if neg_cands:
                negative_prompts.extend(neg_cands)
            if not positive_prompts:
                positive_prompts.append(fallback_texts[0])
                negative_prompts.append(fallback_texts[1])

    if positive_prompts:
        data["prompt"] = "\n\n".join(dict.fromkeys(positive_prompts))
    if negative_prompts:
        data["negative_prompt"] = "\n\n".join(dict.fromkeys(negative_prompts))

    if include_workflow:
        data["workflow"] = parsed

    return data

def _parse_comfyui_litegraph(workflow: Dict[str, Any], include_workflow: bool = True) -> Dict[str, Any]:
    """Parse ComfyUI visual LiteGraph format (workflow.json with nodes array)."""
    data: Dict[str, Any] = {"software": "ComfyUI"}
    nodes = workflow.get("nodes", [])
    if not isinstance(nodes, list):
        if include_workflow:
            data["workflow"] = workflow
        return data

    text_nodes: List[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ntype = node.get("type", "")
        widgets = node.get("widgets_values", [])
        if not isinstance(widgets, list):
            continue

        if "CLIPTextEncode" in ntype and widgets:
            val = widgets[0]
            if isinstance(val, str) and val.strip():
                text_nodes.append(val.strip())

        if ntype in ("CheckpointLoaderSimple", "CheckpointLoader") and widgets:
            if isinstance(widgets[0], str):
                data["model"] = widgets[0]
        elif ntype == "UNETLoader" and widgets:
            if isinstance(widgets[0], str):
                data["model"] = widgets[0]

        if ntype in ("KSampler", "KSamplerAdvanced"):
            # Robust widget extraction with type checks
            for idx, w in enumerate(widgets):
                if idx == 0:
                    data["seed"] = clean_numeric_or_string(str(w))
                elif idx == 2 and isinstance(w, (int, float, str)) and str(w).isdigit():
                    data["steps"] = clean_numeric_or_string(str(w))
                elif idx == 3 and isinstance(w, (int, float, str)):
                    data["cfg_scale"] = clean_numeric_or_string(str(w))
                elif idx == 4 and isinstance(w, str):
                    data["sampler"] = w
                elif idx == 5 and isinstance(w, str):
                    data["scheduler"] = w
                elif idx == 6 and isinstance(w, (int, float, str)):
                    data["denoise"] = clean_numeric_or_string(str(w))

    if text_nodes:
        if len(text_nodes) == 1:
            data["prompt"] = text_nodes[0]
        else:
            neg_cands = [t for t in text_nodes if NEGATIVE_PROMPT_KEYWORDS_REGEX.search(t)]
            pos_cands = [t for t in text_nodes if not NEGATIVE_PROMPT_KEYWORDS_REGEX.search(t)]
            if pos_cands:
                data["prompt"] = "\n\n".join(dict.fromkeys(pos_cands))
            if neg_cands:
                data["negative_prompt"] = "\n\n".join(dict.fromkeys(neg_cands))
            if "prompt" not in data:
                data["prompt"] = text_nodes[0]
                data["negative_prompt"] = text_nodes[1]

    if include_workflow:
        data["workflow"] = workflow

    return data
