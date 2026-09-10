"""Build structural page bundles and expose bounded, local model-reading tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Snapshot:
    def __init__(self, path):
        self.raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(self.raw).hexdigest()
        root = ET.fromstring(self.raw)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Build one XML or all XML files below a directory; no extraction")
    run.add_argument("input", type=Path)
    run.add_argument("--out", type=Path, default=Path("runs"))
    prepare = sub.add_parser("prepare", help="Build a single page bundle in the exact output directory")
    prepare.add_argument("xml", type=Path)
    prepare.add_argument("out", type=Path)
    for name in ("view", "expand", "read", "catalog", "node"):
        cmd = sub.add_parser(name)
        cmd.add_argument("bundle", type=Path)
        if name != "catalog":
            cmd.add_argument("region", type=int, nargs="?", default=None)
        if name in {"view", "expand", "read", "catalog"}:
            cmd.add_argument("--offset", type=int, default=0)
            cmd.add_argument("--limit", type=int, default=8)
        if name == "read":
            cmd.add_argument("--char-offset", type=int, default=0)
            cmd.add_argument("--max-chars", type=int, default=1600)
    args = parser.parse_args()
    try:
        if args.command in {"run", "prepare"}:
            from pipeline import run_batch, run_case
            result = (run_batch(args.input, args.out) if args.command == "run"
                      else run_case(args.xml.resolve(), args.out.resolve()))
            failed = (any(c["status"] == "failed" for c in result["cases"].values())
                      if args.command == "run" else result["status"] == "failed")
        else:
            from page_tree import Bundle
            bundle = Bundle.load(args.bundle)
            if args.command in {"view", "expand"}:
                result = bundle.view(args.region, args.offset, args.limit)
            elif args.command == "read":
                result = bundle.read(args.region, args.offset, args.limit, args.char_offset, args.max_chars)
            elif args.command == "catalog":
                result = bundle.catalog(args.offset, args.limit)
            else:
                result = bundle.node(args.region)
            failed = False
    except (ValueError, KeyError, OSError, ET.ParseError) as error:
        result, failed = {"status": "failed", "error": str(error)}, True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
