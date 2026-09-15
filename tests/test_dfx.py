from pathlib import Path
import tempfile
import unittest
from ..dfx.server import Debugger
from .. import PageSession


class DebuggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.xml=self.root/'nested'/'scroll'/'1.xml';self.xml.parent.mkdir(parents=True)
        self.xml.write_text('<hierarchy><node class="android.widget.Button" bounds="[0,0][10,10]" text="before"/></hierarchy>')
        self.debugger=Debugger(self.root)
        self.case='nested/scroll/1.xml'

    def test_recursive_xml_build_and_public_interface(self):
        self.assertEqual(self.debugger.cases(),[{'id':self.case,'name':self.case}])
        opened=self.debugger.start(self.case);direct=PageSession(self.xml)
        self.assertEqual(opened['initial'],direct.start())
        self.assertEqual(opened['diff']['nodes'],{})
        self.assertEqual(self.debugger.call(opened['session'],'page_node',{'key':1}),direct.bundle.node(1))

    def test_sync_attributes_deletions_and_frozen_baseline(self):
        first=self.debugger.start(self.case)
        self.debugger.call(first['session'],'update_aaid',{'id':1,'value':'12'})
        self.xml.write_text(self.xml.read_text().replace('before','after'))
        updated=self.debugger.start(self.case,first['session'])
        self.assertEqual(updated['diff']['nodes'][1]['attributes']['text'],{'before':'before','after':'after'})
        self.assertEqual(self.debugger.call(updated['session'],'select_aaid',{'aaid':12})['id'],1)
        self.assertEqual(self.debugger.call(first['session'],'page_read',{})['entries'][0]['value'],'before')
        self.xml.write_text(self.xml.read_text().replace('Button','ImageView'))
        replaced=self.debugger.start(self.case,updated['session'])
        self.assertEqual(replaced['diff']['deleted'][0]['id'],1)
        self.assertEqual(replaced['diff']['nodes'][2]['kind'],'replaced')
        self.assertIsNone(self.debugger.call(replaced['session'],'select_aaid',{'aaid':12})['node'])
        independent=self.debugger.start(self.case)
        self.assertEqual(independent['diff']['nodes'],{})

    def test_bad_input_and_failed_sync_leave_baseline_usable(self):
        first=self.debugger.start(self.case)
        for case in ['../',str(self.xml),'missing']:
            with self.assertRaises(ValueError):self.debugger.start(case)
        with self.assertRaises(ValueError):self.debugger.start(self.case,'expired')
        self.xml.write_text('<invalid')
        from xml.etree.ElementTree import ParseError
        with self.assertRaises(ParseError):self.debugger.start(self.case,first['session'])
        self.assertEqual(self.debugger.call(first['session'],'page_node',{'key':1})['id'],1)

    def test_outside_symlink_not_listed(self):
        with tempfile.TemporaryDirectory() as outside:
            target=Path(outside)/'outside.xml';target.write_text(self.xml.read_text())
            (self.root/'escape.xml').symlink_to(target)
            self.assertEqual(len(self.debugger.cases()),1)
