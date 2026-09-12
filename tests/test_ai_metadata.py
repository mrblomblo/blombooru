import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image, PngImagePlugin

from backend.app.utils.ai_metadata import (
    decode_exif_user_comment,
    parse_xmp_packet,
    parse_a1111_parameters,
    parse_comfyui_graph,
    parse_novelai_metadata,
    parse_invokeai_metadata,
    parse_fooocus_metadata,
    extract_prompt_tags,
    normalize_ai_metadata,
    CANONICAL_KEYS,
)
from backend.app.utils.media_helpers import extract_media_metadata, extract_image_metadata


class TestAIMetadata(unittest.TestCase):

    def test_decode_exif_user_comment_unicode_header(self):
        """Test standard EXIF UserComment with UNICODE\\0 header and non-ASCII characters."""
        text = "1girl, 初音ミク, anime style, smiling"
        raw = b"UNICODE\x00" + text.encode("utf-16le")
        decoded = decode_exif_user_comment(raw)
        self.assertEqual(decoded, text)

    def test_decode_exif_user_comment_unicode_be(self):
        """Test EXIF UserComment with UNICODE\\0 header in big-endian."""
        text = "masterpiece, landscape"
        raw = b"UNICODE\x00" + text.encode("utf-16be")
        decoded = decode_exif_user_comment(raw)
        self.assertEqual(decoded, text)

    def test_decode_exif_user_comment_ascii_header(self):
        """Test EXIF UserComment with ASCII\\0\\0\\0 header."""
        text = "masterpiece, solo, 1girl"
        raw = b"ASCII\x00\x00\x00" + text.encode("utf-8")
        decoded = decode_exif_user_comment(raw)
        self.assertEqual(decoded, text)

    def test_decode_exif_user_comment_null_header(self):
        """Test EXIF UserComment with 8 null bytes."""
        text = "best quality, beautiful"
        raw = b"\x00" * 8 + text.encode("utf-8")
        decoded = decode_exif_user_comment(raw)
        self.assertEqual(decoded, text)

    def test_decode_exif_user_comment_raw_string_cleanup(self):
        """Test that string already partially mangled with UNICODE prefix is cleaned."""
        raw_str = "UNICODE1girl, smiling"
        decoded = decode_exif_user_comment(raw_str)
        self.assertEqual(decoded, "1girl, smiling")

    def test_parse_xmp_packet(self):
        """Test standard XMP packet extraction with built-in ElementTree."""
        xmp_xml = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   exif:UserComment="masterpiece, 1girl in forest">
   <dc:description>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">detailed prompt description</rdf:li>
    </rdf:Alt>
   </dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
        parsed = parse_xmp_packet(xmp_xml)
        self.assertIn("UserComment", parsed)
        self.assertEqual(parsed["UserComment"], "masterpiece, 1girl in forest")

    def test_parse_a1111_parameters_multiline_trailing_not_overwriting_prompt(self):
        """Verify trailing parameter lines never overwrite the positive prompt."""
        param_block = """masterpiece, 1girl, smiling, blue sky
Negative prompt: bad anatomy, blurry
Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 123456, Size: 512x768, Model: v1-5
ControlNet 0: "preprocessor: none, model: control_net, weight: 1.0"
Hires resize: 1024x1536, Hires upscaler: Latent
Version: v1.8.0"""
        data = parse_a1111_parameters(param_block)
        self.assertEqual(data["prompt"], "masterpiece, 1girl, smiling, blue sky")
        self.assertEqual(data["negative_prompt"], "bad anatomy, blurry")
        self.assertEqual(data["steps"], 20)
        self.assertEqual(data["sampler"], "Euler a")
        self.assertEqual(data["cfg_scale"], 7)
        self.assertEqual(data["seed"], 123456)
        self.assertEqual(data["width"], 512)
        self.assertEqual(data["height"], 768)
        self.assertEqual(data["model"], "v1-5")
        self.assertEqual(data["version"], "v1.8.0")
        self.assertIn("additional_parameters", data)
        self.assertIn("controlnet_0", data["additional_parameters"])

    def test_parse_comfyui_graph_with_modifier(self):
        """Test ComfyUI graph where conditioning is routed through modifiers."""
        graph = {
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a cute cat sitting on a keyboard"}
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "ugly, blurry, low quality"}
            },
            "10": {
                "class_type": "ConditioningCombine",
                "inputs": {"conditioning_1": ["3", 0], "conditioning_2": ["3", 0]}
            },
            "20": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 99887766,
                    "steps": 25,
                    "cfg": 6.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "positive": ["10", 0],
                    "negative": ["4", 0]
                }
            },
            "30": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sdxl_base_1.0.safetensors"}
            },
            "40": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1024}
            }
        }
        res = parse_comfyui_graph(graph)
        self.assertEqual(res["software"], "ComfyUI")
        self.assertEqual(res["prompt"], "a cute cat sitting on a keyboard")
        self.assertEqual(res["negative_prompt"], "ugly, blurry, low quality")
        self.assertEqual(res["seed"], 99887766)
        self.assertEqual(res["steps"], 25)
        self.assertEqual(res["cfg_scale"], 6.5)
        self.assertEqual(res["sampler"], "dpmpp_2m")
        self.assertEqual(res["scheduler"], "karras")
        self.assertEqual(res["model"], "sdxl_base_1.0.safetensors")
        self.assertEqual(res["width"], 1024)
        self.assertEqual(res["height"], 1024)

    def test_parse_comfyui_litegraph_workflow(self):
        """Test LiteGraph format (workflow.json with nodes array)."""
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CLIPTextEncode",
                    "widgets_values": ["cyberpunk street at night, neon lights"]
                },
                {
                    "id": 2,
                    "type": "CLIPTextEncode",
                    "widgets_values": ["worst quality, blurry"]
                },
                {
                    "id": 3,
                    "type": "KSampler",
                    "widgets_values": [12345, "randomize", 30, 8.0, "euler_ancestral", "normal", 1.0]
                },
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["v1-5-pruned.safetensors"]
                }
            ]
        }
        res = parse_comfyui_graph(workflow)
        self.assertEqual(res["software"], "ComfyUI")
        self.assertEqual(res["prompt"], "cyberpunk street at night, neon lights")
        self.assertEqual(res["negative_prompt"], "worst quality, blurry")
        self.assertEqual(res["seed"], 12345)
        self.assertEqual(res["steps"], 30)
        self.assertEqual(res["cfg_scale"], 8.0)
        self.assertEqual(res["sampler"], "euler_ancestral")
        self.assertEqual(res["scheduler"], "normal")
        self.assertEqual(res["model"], "v1-5-pruned.safetensors")

    def test_parse_novelai_metadata(self):
        """Test NovelAI metadata parser."""
        novelai_comment = {
            "prompt": "1girl, solo, silver hair, red eyes",
            "uc": "lowres, bad anatomy, bad hands, text",
            "steps": 28,
            "sampler": "k_euler",
            "seed": 401928374,
            "scale": 5.0,
            "model": "NovelAI Diffusion V3"
        }
        res = parse_novelai_metadata(novelai_comment)
        self.assertEqual(res["software"], "NovelAI")
        self.assertEqual(res["prompt"], "1girl, solo, silver hair, red eyes")
        self.assertEqual(res["negative_prompt"], "lowres, bad anatomy, bad hands, text")
        self.assertEqual(res["steps"], 28)
        self.assertEqual(res["sampler"], "k_euler")
        self.assertEqual(res["seed"], 401928374)
        self.assertEqual(res["cfg_scale"], 5.0)
        self.assertEqual(res["model"], "NovelAI Diffusion V3")

    def test_parse_invokeai_metadata(self):
        """Test InvokeAI metadata parser."""
        invoke_meta = {
            "positive_prompt": "fantasy castle on a mountain",
            "negative_prompt": "ugly, watermark",
            "model": {"name": "epicrealism_v5"},
            "steps": 35,
            "cfg_scale": 7.5,
            "seed": 554433,
            "width": 768,
            "height": 1024
        }
        res = parse_invokeai_metadata(invoke_meta)
        self.assertEqual(res["software"], "InvokeAI")
        self.assertEqual(res["prompt"], "fantasy castle on a mountain")
        self.assertEqual(res["negative_prompt"], "ugly, watermark")
        self.assertEqual(res["model"], "epicrealism_v5")
        self.assertEqual(res["steps"], 35)
        self.assertEqual(res["cfg_scale"], 7.5)
        self.assertEqual(res["seed"], 554433)
        self.assertEqual(res["width"], 768)
        self.assertEqual(res["height"], 1024)

    def test_extract_prompt_tags_sanitization(self):
        """Test tag extraction and sanitization."""
        raw_prompt = """(masterpiece:1.2), ((1girl)), {best quality}, [solo:0.8],
<lora:detail_tweaker:0.8>, <wildcard:poses>, and black gloves, a blue dress, BREAK, 4k,
a very long natural language sentence describing background details in extreme narrative prose that does not make a tag"""
        tags = extract_prompt_tags(raw_prompt)

        self.assertIn("masterpiece", tags)
        self.assertIn("1girl", tags)
        self.assertIn("best_quality", tags)
        self.assertIn("solo", tags)
        self.assertIn("black_gloves", tags)
        self.assertIn("blue_dress", tags)
        self.assertIn("4k", tags)

        # Directives should be filtered out
        self.assertNotIn("break", tags)
        self.assertNotIn("and", tags)
        self.assertFalse(any("lora" in t for t in tags))
        self.assertFalse(any("wildcard" in t for t in tags))

        # Long natural language narrative should be skipped
        self.assertFalse(any("narrative" in t for t in tags))

    def test_real_swarmui_sample_1(self):
        """Test real SwarmUI sample file 1."""
        p = Path("media/original/SwarmUI/2026-04-20/202604200023-284722543.png")
        if not p.exists():
            self.skipTest(f"Sample file {p} not found")

        meta = extract_media_metadata(p)
        self.assertIn("ai", meta)
        ai = meta["ai"]
        self.assertEqual(ai.get("software"), "SwarmUI")
        self.assertEqual(ai.get("model"), "Anima/animaOfficial_preview3Base")
        self.assertEqual(ai.get("seed"), 284722543)
        self.assertEqual(ai.get("sampler"), "res_multistep")
        self.assertEqual(ai.get("scheduler"), "simple")

        tags = extract_prompt_tags(ai.get("prompt", ""))
        self.assertIn("masterpiece", tags)
        self.assertIn("best_quality", tags)
        self.assertIn("solo", tags)
        self.assertIn("1girl", tags)

    def test_real_swarmui_sample_2_natural_language(self):
        """Test real SwarmUI sample file 2 with natural language prompt."""
        p = Path("media/original/SwarmUI/2026-08-25/202608250009-1575780111.png")
        if not p.exists():
            self.skipTest(f"Sample file {p} not found")

        meta = extract_media_metadata(p)
        self.assertIn("ai", meta)
        ai = meta["ai"]
        self.assertEqual(ai.get("software"), "SwarmUI")
        self.assertEqual(ai.get("model"), "Anima/miaomiaoHarem_anima13")
        self.assertEqual(ai.get("seed"), 1575780111)
        self.assertEqual(ai.get("sampler"), "er_sde")

        tags = extract_prompt_tags(ai.get("prompt", ""))
        self.assertIn("masterpiece", tags)
        self.assertIn("best_quality", tags)
        self.assertIn("safe", tags)
        self.assertIn("black_gloves", tags)
        self.assertIn("brown_eyes", tags)

    def test_real_comfyui_webp_sample(self):
        """Test real ComfyUI WebP sample file."""
        p = Path("media/original/ComfyUI/ComfyUI_00001_.webp")
        if not p.exists():
            self.skipTest(f"Sample file {p} not found")

        meta = extract_media_metadata(p)
        self.assertIn("ai", meta)
        ai = meta["ai"]
        self.assertEqual(ai.get("software"), "ComfyUI")
        self.assertEqual(ai.get("prompt"), "a bearded man eating a hamburger")
        self.assertEqual(ai.get("model"), "Hunyuan/hunyuanVideoSafetensors_comfyDiffusionFP8.safetensors")
        self.assertEqual(ai.get("sampler"), "euler")
        self.assertEqual(ai.get("scheduler"), "normal")
        self.assertEqual(ai.get("seed"), 989485664678804)
        self.assertEqual(ai.get("steps"), 30)

    def test_real_a1111_old_sample(self):
        """Test real Old Automatic1111 PNG sample file."""
        p = Path("media/original/Old/00003-427986097.png")
        if not p.exists():
            self.skipTest(f"Sample file {p} not found")

        meta = extract_media_metadata(p)
        self.assertIn("ai", meta)
        ai = meta["ai"]
        self.assertEqual(ai.get("software"), "Automatic1111")
        self.assertTrue(ai.get("prompt", "").startswith("Beautiful landscape with foliage near point of view"))
        self.assertTrue(ai.get("negative_prompt", "").startswith("text, nsfw, naked"))
        self.assertEqual(ai.get("steps"), 40)
        self.assertEqual(ai.get("sampler"), "Euler a")
        self.assertEqual(ai.get("seed"), 427986097)
        self.assertEqual(ai.get("cfg_scale"), 7)
        self.assertEqual(ai.get("model"), "realisticVisionV20_v20NoVAE")
        self.assertEqual(ai.get("model_hash"), "c0d1994c73")

    def test_extract_prompt_tags_prose_with_internal_commas(self):
        """Verify that natural language prose containing internal commas does not leak fragments as tags."""
        raw_prompt = (
            "features a cheerful, dark-haired girl with a dynamic, blurred effect. "
            "Lighting is artificial, creating a vibrant atmosphere, black_gloves, brown_eyes"
        )
        tags = extract_prompt_tags(raw_prompt)
        self.assertIn("black_gloves", tags)
        self.assertIn("brown_eyes", tags)
        # Verify prose clauses were rejected
        self.assertNotIn("cheerful", tags)
        self.assertNotIn("dynamic", tags)
        self.assertNotIn("blurred_effect._lighting_is_artificial", tags)
        self.assertNotIn("creating_a_vibrant", tags)
        self.assertNotIn("atmosphere", tags)

    def test_extract_prompt_tags_preserves_danbooru_parens(self):
        """Verify Danbooru disambiguation parens like star_(sky) are preserved, while outer weighting parens are stripped."""
        raw_prompt = "1girl, star_(sky), fate_(series), ((solo)), {smiling:1.1}, [blue_eyes:0.9]"
        tags = extract_prompt_tags(raw_prompt)
        self.assertIn("1girl", tags)
        self.assertIn("star_(sky)", tags)
        self.assertIn("fate_(series)", tags)
        self.assertIn("solo", tags)
        self.assertIn("smiling", tags)
        self.assertIn("blue_eyes", tags)
        # Ensure no trailing paren was stripped
        self.assertNotIn("star_(sky", tags)
        self.assertNotIn("fate_(series", tags)

    def test_extract_prompt_tags_space_separated_fallback(self):
        """Verify purely space-separated tag dump without commas or newlines is correctly split."""
        raw_prompt = "1girl solo brown_hair blue_eyes looking_at_viewer"
        tags = extract_prompt_tags(raw_prompt)
        self.assertEqual(tags, ["1girl", "solo", "brown_hair", "blue_eyes", "looking_at_viewer"])

    def test_a1111_out_of_order_controlnet(self):
        """Verify A1111 parser detects parameter block even when extensions (like ControlNet) precede standard keys."""
        param_block = """beautiful girl in autumn garden
Negative prompt: ugly, deformed
ControlNet 0: "preprocessor: canny, model: control_v11p_sd15_canny [d14c016b], weight: 1.0"
Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 87654321, Size: 512x768, Model: revAnimated_v122"""
        data = parse_a1111_parameters(param_block)
        self.assertEqual(data["software"], "Automatic1111")
        self.assertEqual(data["prompt"], "beautiful girl in autumn garden")
        self.assertEqual(data["negative_prompt"], "ugly, deformed")
        self.assertEqual(data["steps"], 25)
        self.assertEqual(data["sampler"], "DPM++ 2M Karras")
        self.assertEqual(data["seed"], 87654321)
        self.assertEqual(data["width"], 512)
        self.assertEqual(data["height"], 768)
        self.assertEqual(data["model"], "revAnimated_v122")
        self.assertIn("controlnet_0", data.get("additional_parameters", {}))

    def test_invokeai_guards(self):
        """Verify InvokeAI parser handles list of strings and dict models without name key."""
        # 1. String list prompt in image
        raw1 = {
            "image": {
                "prompt": ["line 1 of prompt", "line 2 of prompt"],
                "steps": 20
            }
        }
        res1 = parse_invokeai_metadata(raw1)
        self.assertEqual(res1["prompt"], "line 1 of prompt\nline 2 of prompt")
        self.assertEqual(res1["steps"], 20)

        # 2. Model dict with model_name instead of name
        raw2 = {
            "positive_prompt": "fantasy landscape",
            "model": {"model_name": "realistic_vision", "base": "sd1"}
        }
        res2 = parse_invokeai_metadata(raw2)
        self.assertEqual(res2["model"], "realistic_vision")

    def test_fooocus_json_metadata(self):
        """Test Fooocus JSON metadata parsing."""
        raw = {
            "prompt": "majestic dragon over misty mountains",
            "negative_prompt": "blurry, low quality",
            "base_model": "juggernautXL_v9",
            "sampler": "dpmpp_2m_sde_gpu",
            "scheduler": "karras",
            "seed": 987654,
            "steps": 30,
            "guidance_scale": 7.0,
            "resolution": "(1152, 896)",
            "fooocus_v2_expansion": "photorealistic details"
        }
        res = parse_fooocus_metadata(raw)
        self.assertEqual(res["software"], "Fooocus")
        self.assertEqual(res["prompt"], "majestic dragon over misty mountains")
        self.assertEqual(res["negative_prompt"], "blurry, low quality")
        self.assertEqual(res["model"], "juggernautXL_v9")
        self.assertEqual(res["sampler"], "dpmpp_2m_sde_gpu")
        self.assertEqual(res["scheduler"], "karras")
        self.assertEqual(res["seed"], 987654)
        self.assertEqual(res["steps"], 30)
        self.assertEqual(res["cfg_scale"], 7.0)
        self.assertEqual(res["width"], 1152)
        self.assertEqual(res["height"], 896)
        self.assertEqual(res["additional_parameters"]["fooocus_v2_expansion"], "photorealistic details")

        # Also test normalize_ai_metadata auto-detect
        norm = normalize_ai_metadata({"parameters": raw})
        self.assertEqual(norm["software"], "Fooocus")
        self.assertEqual(norm["seed"], 987654)

    def test_fooocus_text_metadata(self):
        """Test Fooocus text parameter block parsing."""
        text = """neon cyberpunk alleyway at dusk
Negative prompt: ugly, cartoon
Resolution: 1024*1024
Base Model: juggernautXL
Sampler: dpmpp_2m
Schedule type: karras
Seed: 54321
Steps: 28
Guidance Scale: 6.5
Fooocus V2 Expansion: cinematic neon glow"""
        res = parse_fooocus_metadata(text)
        self.assertEqual(res["software"], "Fooocus")
        self.assertEqual(res["prompt"], "neon cyberpunk alleyway at dusk")
        self.assertEqual(res["negative_prompt"], "ugly, cartoon")
        self.assertEqual(res["model"], "juggernautXL")
        self.assertEqual(res["width"], 1024)
        self.assertEqual(res["height"], 1024)
        self.assertEqual(res["seed"], 54321)
        self.assertEqual(res["steps"], 28)
        self.assertEqual(res["cfg_scale"], 6.5)
        self.assertIn("fooocus_v2_expansion", res["additional_parameters"])

    def test_xmp_description_rdf_alt_resolution(self):
        """Verify XMP parser extracts dc:description with nested rdf:Alt and rdf:li."""
        xmp_xml = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:description>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">a peaceful forest with sunlight rays</rdf:li>
    </rdf:Alt>
   </dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""
        parsed = parse_xmp_packet(xmp_xml)
        self.assertIn("Description", parsed)
        self.assertEqual(parsed["Description"], "a peaceful forest with sunlight rays")

    def test_extract_image_metadata_stats_and_deduplication(self):
        """Verify extract_image_metadata returns width, height, file_size, and deduplicates workflow."""
        p = Path("media/original/SwarmUI/2026-04-20/202604200023-284722543.png")
        if not p.exists():
            self.skipTest(f"Sample file {p} not found")

        meta = extract_image_metadata(p)
        self.assertEqual(meta.get("file_type"), "image")
        self.assertEqual(meta.get("mime_type"), "image/png")
        self.assertIsInstance(meta.get("file_size"), int)
        self.assertGreater(meta.get("file_size"), 0)
        self.assertIsInstance(meta.get("width"), int)
        self.assertIsInstance(meta.get("height"), int)
        self.assertGreater(meta.get("width"), 0)
        self.assertGreater(meta.get("height"), 0)

    def test_extract_prompt_tags_grouped_weighted_with_internal_commas(self):
        """Verify grouped and weighted tags with internal commas are split correctly."""
        # 1. Standard grouped negative tags with weight
        raw_prompt = "(worst quality, low quality, normal quality:1.4), lowres, bad anatomy"
        tags = extract_prompt_tags(raw_prompt)
        self.assertEqual(tags, ["worst_quality", "low_quality", "normal_quality", "lowres", "bad_anatomy"])

        # 2. Nested grouped tags
        nested_prompt = "((worst quality, (low quality:1.1), normal quality:1.4))"
        nested_tags = extract_prompt_tags(nested_prompt)
        self.assertEqual(nested_tags, ["worst_quality", "low_quality", "normal_quality"])

        # 3. Grouped prose in parens should not leak fragments
        prose_prompt = "(features a cheerful, dark-haired girl with a dynamic, blurred effect:1.2), black_gloves"
        prose_tags = extract_prompt_tags(prose_prompt)
        self.assertEqual(prose_tags, ["black_gloves"])

    def test_comfyui_prompt_chunk_collision_and_deduplication(self):
        """Verify ComfyUI raw prompt chunk does not collide with metadata prompt or duplicate workflow graph."""
        graph = {
            "3": {
                "class_type": "KSampler",
                "inputs": {"seed": 12345, "steps": 20, "cfg": 8.0, "positive": ["4", 0]}
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a cute kitten on a cloud"}
            }
        }
        litegraph = {"nodes": [{"id": 1, "type": "CLIPTextEncode"}]}

        # Case A: PNG with only 'prompt' chunk (API graph)
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            info = PngImagePlugin.PngInfo()
            info.add_text("prompt", json.dumps(graph))
            img = Image.new("RGB", (32, 32), color="red")
            img.save(f.name, pnginfo=info)

            res = extract_image_metadata(Path(f.name))
            # 'prompt' must be extracted human text, never a dict
            self.assertIsInstance(res.get("prompt"), str)
            self.assertEqual(res.get("prompt"), "a cute kitten on a cloud")
            self.assertEqual(res.get("ai", {}).get("prompt"), "a cute kitten on a cloud")
            self.assertEqual(res.get("ai", {}).get("software"), "ComfyUI")
            # Workflow graph should exist in ai.workflow, but not duplicated at root
            self.assertIn("workflow", res.get("ai", {}))
            self.assertNotIn("workflow", res)

        # Case B: PNG with both 'prompt' chunk (API graph) and 'workflow' chunk (LiteGraph)
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            info = PngImagePlugin.PngInfo()
            info.add_text("prompt", json.dumps(graph))
            info.add_text("workflow", json.dumps(litegraph))
            img = Image.new("RGB", (32, 32), color="red")
            img.save(f.name, pnginfo=info)

            res = extract_image_metadata(Path(f.name))
            self.assertIsInstance(res.get("prompt"), str)
            self.assertEqual(res.get("prompt"), "a cute kitten on a cloud")
            self.assertEqual(res.get("ai", {}).get("prompt"), "a cute kitten on a cloud")
            # Visual LiteGraph is at root metadata['workflow'], deduplicated from ai['workflow']
            self.assertIn("workflow", res)
            self.assertNotIn("workflow", res.get("ai", {}))

    def test_canonical_keys_includes_prompt_tags(self):
        """Verify CANONICAL_KEYS includes prompt_tags."""
        self.assertIn("prompt_tags", CANONICAL_KEYS)

    def test_normalize_ai_metadata_populates_prompt_tags(self):
        """Verify normalize_ai_metadata populates prompt_tags for detected AI generator outputs."""
        sample_meta = {
            "Comment": json.dumps({
                "prompt": "1girl, solo, silver hair, red eyes, dynamic pose",
                "steps": 28,
                "model": "NovelAI Diffusion V3"
            })
        }
        res = normalize_ai_metadata(sample_meta)
        self.assertEqual(res.get("software"), "NovelAI")
        self.assertIn("prompt_tags", res)
        self.assertIn("1girl", res["prompt_tags"])
        self.assertIn("silver_hair", res["prompt_tags"])
        self.assertIn("red_eyes", res["prompt_tags"])

    def test_normalize_ai_metadata_fallback_prompt_tags(self):
        """Verify normalize_ai_metadata fallback with raw prompt string extracts prompt_tags."""
        sample_meta = {
            "prompt": "masterpiece, 1boy, blue sky, outdoors"
        }
        res = normalize_ai_metadata(sample_meta)
        self.assertEqual(res.get("prompt"), "masterpiece, 1boy, blue sky, outdoors")
        self.assertIn("prompt_tags", res)
        self.assertEqual(res["prompt_tags"], ["masterpiece", "1boy", "blue_sky", "outdoors"])

if __name__ == "__main__":
    unittest.main()
