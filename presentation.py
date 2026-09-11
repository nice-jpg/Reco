"""Model-facing regions: operation boundaries and visual types, never raw IDs."""
import re


WRAPPERS = {"FrameLayout", "LinearLayout", "RelativeLayout", "ViewGroup", "ConstraintLayout"}
LABELS = {"page": "page", "list": "list", "scroll": "scrollable", "pager": "page switcher",
          "input": "text input", "button": "button", "toggle": "selection control",
          "click": "clickable", "long_press": "long-press",
          "text": "text", "image": "image", "visual": "visual"}


def box(attributes):
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", attributes.get("bounds", ""))
    return list(map(int, match.groups())) if match else None


def envelope(boxes):
    boxes = [b for b in boxes if b and b[2] > b[0] and b[3] > b[1]]
    return ([min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None)


def boundary(a, leaf):
    """No text, description, hint, resource-id or bounds in boundary decisions."""
    name = a.get("class", "").split(".")[-1]
    if name in {"EditText", "AutoCompleteTextView", "SearchView"}:
        return "input", "action", "input"
    if "RecyclerView" in name or name in {"ListView", "GridView"}:
        return "list", "action", "list"
    if "ViewPager" in name:
        return "pager", "action", "pager"
    if a.get("scrollable") == "true" or "ScrollView" in name:
        return "scroll", "action", "scroll"
    if a.get("checkable") == "true" or name in {"CheckBox", "RadioButton", "Switch", "SwitchCompat", "ToggleButton", "Spinner"}:
        return "toggle", "action", "toggle"
    if name in {"Button", "ImageButton"}:
        return "button", "action", "button"
    if a.get("clickable") == "true":
        return "click", "action", "click"
    if a.get("long-clickable") == "true":
        return "long_press", "action", "long_press"
    if name.endswith("TextView"):
        return "text", "visual", "text"
    if name.endswith("ImageView"):
        return "image", "visual", "image"
    if leaf and name not in WRAPPERS:
        return "visual", "visual", name
    return None


class Regions:
    def __init__(self, index, payload):
        self.index, self.payload = index, payload["entries"]
        self.nodes = index["nodes"]
        children = {k: [] for k in self.nodes}
        roots = []
        for k, n in self.nodes.items():
            if n["parent"] is None:
                roots.append(k)
            else:
                children[n["parent"]].append(k)
        self.regions = {0: {"role": "page", "category": "page", "type": "page", "children": [],
                            "sources": [], "bounds": envelope([box(self.nodes[k]["attributes"]) for k in roots]),
                            "state": {}}}
        counter = 0

        def visit(source, parent):
            nonlocal counter
            a = self.nodes[source]["attributes"]
            role = boundary(a, not children[source])
            if role:
                counter += 1
                current = counter
                self.regions[current] = {"role": role[0], "category": role[1], "type": role[2],
                    "children": [], "sources": [], "bounds": box(a),
                    "state": {k: a[k] == "true" for k in ("enabled", "selected", "checked") if k in a}}
                self.regions[parent]["children"].append(current)
            else:
                current = parent
            self.regions[current]["sources"].append(source)
            for child in children[source]:
                visit(child, current)

        for source in roots:
            visit(source, 0)

        def merge(key):
            region = self.regions[key]
            result = []
            for child in region["children"]:
                merge(child)
                item = self.regions[child]
                if (region["category"] == item["category"] == "visual"
                        and region["type"] == item["type"]):
                    region["sources"].extend(item["sources"])
                    result.extend(item["children"])
                    del self.regions[child]
                    continue
                previous = self.regions[result[-1]] if result else None
                if (previous and previous["category"] == item["category"] == "visual"
                        and previous["type"] == item["type"]
                        and not previous["children"] and not item["children"]):
                    previous["sources"].extend(item["sources"])
                    previous["bounds"] = envelope([previous["bounds"], item["bounds"]])
                    del self.regions[child]
                else:
                    result.append(child)
            region["children"] = result

        merge(0)
        # Dense public integers, independent of raw n/g keys and fingerprints.
        mapping = {old: new for new, old in enumerate(self.regions)}
        self.regions = {mapping[k]: {**r, "children": [mapping[c] for c in r["children"]]}
                        for k, r in self.regions.items()}
        self.owner = {}
        self.members = {}
        self.descendant_counts = {}

        def finish(key):
            r = self.regions[key]
            members = set(r["sources"])
            for source in r["sources"]:
                self.owner[source] = key
            for child in r["children"]:
                members.update(finish(child))
            self.members[key] = members
            self.descendant_counts[key] = sum(1 + self.descendant_counts[c] for c in r["children"])
            return members

        finish(0)
        self._entries = {k: [i for i, e in enumerate(self.payload) if e["node"] in members]
                         for k, members in self.members.items()}

    def key(self, key):
        key = 0 if key is None else key
        if type(key) is not int or key not in self.regions:
            raise ValueError("Unknown public region ID")
        return key

    @staticmethod
    def paginate(offset, limit, total):
        if not 1 <= limit <= 50 or not 0 <= offset <= total:
            raise ValueError("Invalid pagination")

    def summary_text(self, key):
        """Display-only text assembly; never used for region partitioning."""
        label = LABELS[self.regions[key]["role"]]
        fragments, seen = [], set()
        for number in self._entries[key]:
            text = " ".join(self.payload[number]["value"].split())
            if text and text not in seen:
                fragments.append(text)
                seen.add(text)
        if not fragments:
            return label
        content = " ".join(fragments[:6])
        truncated = len(fragments) > 6 or len(content) > 120
        return label + ": " + content[:120].rstrip() + ("…" if truncated else "")

    def summary(self, key):
        r = self.regions[key]
        value = {"id": key, "summary": self.summary_text(key), "sub-regions": self.descendant_counts[key]}
        if r["children"]:
            value["expandable"] = True
        return value

    def view(self, key=None, offset=0, limit=8):
        key = self.key(key)
        r = self.regions[key]
        children = r["children"]
        self.paginate(offset, limit, len(children))
        end = min(len(children), offset + limit)
        output = {"id": key, "bounds": r["bounds"], "summary": self.summary_text(key),
                  "sub-regions": self.descendant_counts[key], "regions": [self.summary(c) for c in children[offset:end]]}
        if end < len(children):
            output["next_offset"] = end
        return output

    def catalog(self, offset=0, limit=8):
        keys = [k for k, r in self.regions.items() if r["role"] in {"input", "list", "scroll", "pager"}]
        self.paginate(offset, limit, len(keys))
        end = min(len(keys), offset + limit)
        output = {"regions": [self.summary(k) for k in keys[offset:end]]}
        if end < len(keys):
            output["next_offset"] = end
        return output

    def read(self, key=None, offset=0, limit=8, char_offset=0, max_chars=1600):
        key = self.key(key)
        entries = self._entries[key]
        self.paginate(offset, limit, len(entries))
        if not 1 <= max_chars <= 16000 or char_offset < 0:
            raise ValueError("Invalid character budget or cursor")
        if ((offset == len(entries) and char_offset)
                or (offset < len(entries) and char_offset >= len(self.payload[entries[offset]]["value"]))):
            raise ValueError("Invalid character cursor")
        result, budget, i, start = [], max_chars, offset, char_offset
        while i < len(entries) and len(result) < limit and budget:
            number = entries[i]
            e = self.payload[number]
            value = e["value"][start:start + budget]
            result.append({"item": number, "type": {"text": "text", "content-desc": "description", "hint": "hint"}[e["attribute"]],
                           "value": value, "char_range": [start, start + len(value)]})
            budget -= len(value)
            start += len(value)
            if start == len(e["value"]):
                i, start = i + 1, 0
        output = {"id": key, "entries": result}
        if i < len(entries):
            output["next"] = {"offset": i, "char_offset": start}
        return output

    def details(self, key):
        key = self.key(key)
        r = self.regions[key]
        return {**self.summary(key), "bounds": r["bounds"], **r["state"]}

    def export(self, key=0):
        r = self.regions[key]
        return {"id": key, "bounds": r["bounds"], "summary": self.summary_text(key),
                "sub-regions": self.descendant_counts[key], "regions": [self.export(c) for c in r["children"]]}

    def max_depth(self, key=0):
        return max((1 + self.max_depth(c) for c in self.regions[key]["children"]), default=0)
