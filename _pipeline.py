"""Build local structural bundles; semantic extraction belongs to the model."""
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from ._xml import Snapshot, write_json
from ._page_tree import Bundle


def run_case(xml, output):
    output.mkdir(parents=True, exist_ok=True)
    for name in ("result.json", "annotation.json", "target.txt", "verification.json", "compact.txt",
                 "overview.txt", "index.json", "candidates.json", "metrics.json", "status.json",
                 "tree.json", "payload.json", "overview.json", "catalog.json", "regions.json", "navigation_example.json"):
        (output / name).unlink(missing_ok=True)
    started = time.perf_counter()
    try:
        snapshot = Snapshot(xml)
        bundle = Bundle.from_snapshot(snapshot)
        bundle.save(output)
        def internal_depth(key):
            return max((1 + internal_depth(c) for c in bundle.tree["regions"][key]["children"]), default=0)
        metrics = {"source_nodes": len(snapshot.nodes), "regions": len(bundle.tree["regions"]),
                   "internal_max_depth": internal_depth(bundle.tree["root"]),
                   "public_regions": len(bundle.presentation.regions),
                   "public_max_depth": bundle.presentation.max_depth(),
                   "raw_utf8_bytes": len(snapshot.raw),
                   "overview_utf8_bytes": (output / "overview.json").stat().st_size,
                   "catalog_page_utf8_bytes": (output / "catalog.json").stat().st_size,
                   "payload_utf8_bytes": (output / "payload.json").stat().st_size,
                   "token_count": None, "model_calls": 0}
        write_json(output / "metrics.json", metrics)
        report = {"status": "ready", "root": 0, "metrics": metrics}
    except (ValueError, KeyError, OSError, ET.ParseError) as error:
        report = {"status": "failed", "error": str(error)}
    report.update({"xml": str(xml.resolve()), "output": str(output.resolve()),
                   "elapsed_seconds": round(time.perf_counter() - started, 4)})
    write_json(output / "status.json", report)
    return report


def run_batch(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if source.is_file():
        paths = [source]
    elif source.is_dir():
        paths = sorted(p for p in source.rglob("*.xml") if out not in p.parents)
    else:
        raise ValueError(f"Input does not exist: {source}")
    if not paths:
        raise ValueError("No XML cases found")
    base = source.parent if source.is_file() else source
    cases = {}
    for xml in paths:
        case_id = xml.relative_to(base).with_suffix("").as_posix()
        cases[case_id] = run_case(xml, out / case_id)
    summary = {"cases": cases, "case_count": len(cases),
               "note": "Ready means a lossless evidence bundle is built, not that business data has been extracted."}
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "summary.json", summary)
    return summary
