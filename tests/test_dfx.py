from pathlib import Path
import tempfile
import unittest

from ..dfx.server import Debugger
from .. import PageSession
from .._page_tree import Bundle
from .._xml import Snapshot


class DebuggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runs = Path(self.tmp.name) / "runs"
        self.xml = Path(self.tmp.name) / "source.xml"
        self.xml.write_text('<hierarchy><node class="android.widget.TextView" bounds="[-100,-50][80,90]" text="文本🧪"/></hierarchy>')
        Bundle.from_snapshot(Snapshot(self.xml)).save(self.runs / "sample/page")
        self.debugger = Debugger(self.runs)

    def test_reuses_bundle_and_preserves_model_interface_output(self):
        self.assertEqual(self.debugger.cases(), [{"id": "sample/page", "name": "sample/page"}])
        opened = self.debugger.start("sample/page")
        direct = PageSession.load(self.runs / "sample/page")
        self.assertEqual(opened["initial"], direct.start())
        for name, args in [("page_view", {}), ("page_catalog", {}), ("page_read", {"key": 0}), ("page_node", {"key": 1})]:
            self.assertEqual(self.debugger.call(opened["session"], name, args), direct.call(name, args))

    def test_arbitrary_paths_and_nonpublic_calls_rejected(self):
        for name in ("../", str(self.xml), "missing"):
            with self.assertRaises(ValueError):
                self.debugger.start(name)
        opened = self.debugger.start("sample/page")
        with self.assertRaises(ValueError):
            self.debugger.call(opened["session"], "raw_index", {})
        with self.assertRaises(ValueError):
            self.debugger.call("bad", "page_view", {})

    def test_session_remains_bound_to_its_loaded_snapshot(self):
        old = self.debugger.start("sample/page")
        self.xml.write_text(self.xml.read_text().replace("文本🧪", "更新后"))
        Bundle.from_snapshot(Snapshot(self.xml)).save(self.runs / "sample/page")
        new = self.debugger.start("sample/page")
        self.assertEqual(self.debugger.call(old["session"], "page_read", {})["entries"][0]["value"], "文本🧪")
        self.assertEqual(self.debugger.call(new["session"], "page_read", {})["entries"][0]["value"], "更新后")
