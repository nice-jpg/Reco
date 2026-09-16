"""Build structural page bundles and expose bounded, local model-reading tools."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Snapshot:
    def __init__(self, xml: str):
        if not isinstance(xml, str):
            raise TypeError("Expected XML content as a string")
        self.raw = xml.encode("utf-8")
        self.sha256 = hashlib.sha256(self.raw).hexdigest()
        root = ET.fromstring(xml)
        elements = list(root.iter("node"))
        if not elements:
            raise ValueError("No Android node elements")
        self.ids = {element: f"n{i}" for i, element in enumerate(elements)}
        self.nodes = {self.ids[e]: e for e in elements}
        self.parents = {self.ids[c]: self.ids[p] for p in elements for c in p if c in self.ids}

    def bounds(self, key):
        match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]",
                             self.nodes[key].get("bounds", ""))
        return list(map(int, match.groups())) if match else None
