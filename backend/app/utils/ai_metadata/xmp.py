import re
import xml.etree.ElementTree as ET
from typing import Any, Dict

def parse_xmp_packet(xmp_data: Any) -> Dict[str, Any]:
    """Extract metadata fields from an XMP packet string or bytes."""
    results: Dict[str, Any] = {}
    if not xmp_data:
        return results

    if isinstance(xmp_data, bytes):
        try:
            xmp_str = xmp_data.decode("utf-8", errors="replace")
        except Exception:
            return results
    elif isinstance(xmp_data, str):
        xmp_str = xmp_data
    else:
        return results

    xmp_str = xmp_str.strip()
    xmp_str = re.sub(r"<\?xpacket[^>]*\?>", "", xmp_str).strip()
    if not xmp_str:
        return results

    try:
        root = ET.fromstring(xmp_str)
    except ET.ParseError:
        start = xmp_str.find("<x:xmpmeta")
        if start == -1:
            start = xmp_str.find("<rdf:RDF")
        end = xmp_str.rfind("</x:xmpmeta>")
        if end != -1:
            end += len("</x:xmpmeta>")
        elif xmp_str.rfind("</rdf:RDF>") != -1:
            end = xmp_str.rfind("</rdf:RDF>") + len("</rdf:RDF>")

        if start != -1 and end != -1 and start < end:
            try:
                root = ET.fromstring(xmp_str[start:end])
            except ET.ParseError:
                return results
        else:
            return results

    def local_name(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def extract_text_or_container(elem: ET.Element) -> str:
        # Check direct text
        if elem.text and elem.text.strip():
            return elem.text.strip()
        # Check for rdf:Alt / rdf:Seq / rdf:Bag / rdf:li children
        li_texts = []
        for child in elem.iter():
            if local_name(child.tag) == "li" and child.text and child.text.strip():
                li_texts.append(child.text.strip())
        if li_texts:
            return "\n".join(li_texts)
        return ""

    target_tags = {"UserComment", "parameters", "prompt", "description", "Description", "Comment"}

    for elem in root.iter():
        tag = local_name(elem.tag)
        if tag in target_tags:
            content = extract_text_or_container(elem)
            if content and tag not in results:
                results[tag] = content

        for attr_key, attr_val in elem.attrib.items():
            attr_name = local_name(attr_key)
            if attr_name in target_tags and attr_val and str(attr_val).strip():
                if attr_name not in results:
                    results[attr_name] = str(attr_val).strip()

    return results
