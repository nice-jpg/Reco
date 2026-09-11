"""Text-blind structural partitioning plus evidence-preserving model views.

Class, hierarchy, state and bounds are the only partition/signature inputs.
text/content-desc/hint/resource-id are never read by Builder.
Synthetic groups only wrap contiguous siblings: raw ancestry remains in index.
"""
import hashlib
import json
from bisect import bisect_left
from pathlib import Path

from ._xml import write_json
from ._presentation import Regions


CONTAINERS = {"FrameLayout", "LinearLayout", "RelativeLayout", "ViewGroup"}
STATE_KEYS = ("clickable", "long-clickable", "scrollable", "checkable", "checked",
              "selected", "focused", "focusable", "enabled", "visible-to-user", "displayed")
PAYLOAD_KEYS = ("text", "content-desc", "hint")


def positive(box):
    return bool(box and box[2] > box[0] and box[3] > box[1])


def union(boxes):
    boxes = [b for b in boxes if positive(b)]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def layout(boxes):
    if not boxes:
        return "leaf"
    if len(boxes) == 1:
        return "single"
    if not all(positive(b) for b in boxes):
        return "unknown_geometry"
    if all(a[2] <= b[0] for a, b in zip(boxes, boxes[1:])):
        return "horizontal"
    if all(a[3] <= b[1] for a, b in zip(boxes, boxes[1:])):
        return "vertical"
    return "overlap_or_mixed"


class Builder:
    def __init__(self, snapshot, fanout=8):
        self.snapshot = snapshot
        self.regions = {}
        self.owner = {}
        self.fanout = fanout
        self.serial = 0

    def virtual(self, children, kind):
        self.serial += 1
        key = f"g{self.serial}"
        members = [self.regions[c] for c in children]
        self.regions[key] = {
            "kind": kind, "source_nodes": [], "children": children,
            "bounds": union([r["bounds"] for r in members]), "class": None,
            "states": {}, "layout": layout([r["bounds"] for r in members]),
            "shape": members[0]["shape"] if kind == "repeated_structure" else None,
        }
        return key

    def group(self, children):
        # Equal structural fingerprints are hints only, not proof of semantics.
        grouped = []
        i = 0
        while i < len(children):
            j = i + 1
            while j < len(children) and self.regions[children[j]]["shape"] == self.regions[children[i]]["shape"]:
                j += 1
            grouped.append(self.virtual(children[i:j], "repeated_structure") if j - i >= 2 else children[i])
            i = j
        # Local fallback for heterogeneous/high-fanout nodes: ordered range groups.
        while len(grouped) > self.fanout:
            grouped = [self.virtual(grouped[i:i + self.fanout], "ordered_range")
                       for i in range(0, len(grouped), self.fanout)]
        return grouped

    def build_node(self, element):
        snapshot = self.snapshot
        key = snapshot.ids[element]
        chain = [key]
        while len(element) == 1:
            child = element[0]
            if (child not in snapshot.ids or element.get("class", "").split(".")[-1] not in CONTAINERS
                    or snapshot.bounds(snapshot.ids[element]) != snapshot.bounds(snapshot.ids[child])
                    or any(element.get(k) == "true" for k in STATE_KEYS if k != "enabled")
                    or element.get("enabled") == "false"
                    or any(k in element.attrib for k in ("visible-to-user", "displayed"))):
                break
            element = child
            chain.append(snapshot.ids[element])
        children = [self.build_node(c) for c in element if c in snapshot.ids]
        box = snapshot.bounds(snapshot.ids[element])
        states = {k: element.get(k) for k in STATE_KEYS if k in element.attrib}
        orientation = layout([self.regions[c]["bounds"] for c in children])
        relative = []
        for child in children:
            b = self.regions[child]["bounds"]
            if positive(box) and b:
                relative.append([round((b[i] - box[i % 2]) / (box[i % 2 + 2] - box[i % 2]) * 20)
                                 for i in range(4)])
            else:
                relative.append(None)
        signature = [element.get("class"), states, orientation,
                     [[self.regions[c]["shape"], rel] for c, rel in zip(children, relative)]]
        shape = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]
        self.regions[key] = {"kind": "node", "source_nodes": chain, "class": element.get("class"),
                             "states": states, "bounds": box, "layout": orientation, "shape": shape,
                             "children": self.group(children)}
        for source in chain:
            self.owner[source] = key
        return key

    def build(self):
        roots = [self.build_node(e) for key, e in self.snapshot.nodes.items() if key not in self.snapshot.parents]
        root = roots[0] if len(roots) == 1 else self.virtual(roots, "window_roots")

        def finish(key, parent=None):
            region = self.regions[key]
            region["parent"] = parent
            indices = [int(k[1:]) for k in region["source_nodes"]]
            count = len(indices)
            for child in region["children"]:
                start, end, size = finish(child, key)
                indices.extend([start, end - 1])
                count += size
            region["span"] = [min(indices), max(indices) + 1]
            region["source_count"] = count
            if region["span"][1] - region["span"][0] != count:
                raise ValueError("Noncontiguous structural region")
            return *region["span"], count

        finish(root)
        return {"version": 1, "snapshot_sha256": self.snapshot.sha256, "root": root,
                "regions": self.regions, "node_owner": self.owner}


class Bundle:
    def __init__(self, tree, index, payload):
        self.tree, self.index, self.payload = tree, index, payload
        if not (tree["snapshot_sha256"] == index["snapshot_sha256"] == payload["snapshot_sha256"]):
            raise ValueError("Bundle snapshot mismatch")
        self._payload_positions = [int(e["node"][1:]) for e in payload["entries"]]
        self.presentation = Regions(index, payload)

    @classmethod
    def from_snapshot(cls, snapshot):
        tree = Builder(snapshot).build()
        index = {"snapshot_sha256": snapshot.sha256,
                 "nodes": {k: {"parent": snapshot.parents.get(k), "attributes": e.attrib}
                           for k, e in snapshot.nodes.items()}}
        entries = [{"node": key, "attribute": attr, "value": e.get(attr)}
                   for key, e in snapshot.nodes.items() for attr in PAYLOAD_KEYS if e.get(attr)]
        return cls(tree, index, {"snapshot_sha256": snapshot.sha256, "entries": entries})

    @classmethod
    def load(cls, path):
        return cls(*(json.loads((Path(path) / name).read_text(encoding="utf-8"))
                     for name in ("tree.json", "index.json", "payload.json")))

    def save(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        for name, value in (("tree.json", self.tree), ("index.json", self.index), ("payload.json", self.payload)):
            write_json(path / name, value)
        write_json(path / "regions.json", self.presentation.export())
        write_json(path / "overview.json", self.view())
        write_json(path / "catalog.json", self.catalog())

    def resolve(self, key):
        key = self.tree["root"] if key is None else key
        key = self.tree["node_owner"].get(key, key)
        if key not in self.tree["regions"]:
            raise ValueError(f"Unknown region: {key}")
        return key

    def entries(self, key):
        start, end = self.tree["regions"][key]["span"]
        return self.payload["entries"][bisect_left(self._payload_positions, start):
                                       bisect_left(self._payload_positions, end)]

    def view(self, key=None, offset=0, limit=-1):
        return self.presentation.view(key, offset, limit)

    def catalog(self, offset=0, limit=-1):
        return self.presentation.catalog(offset, limit)

    def read(self, key=None, offset=0, limit=-1, char_offset=0, max_chars=-1):
        return self.presentation.read(key, offset, limit, char_offset, max_chars)

    def node(self, key):
        return self.presentation.details(key)
