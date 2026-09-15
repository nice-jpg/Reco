from pathlib import Path
import tempfile
import unittest

from .. import PageSession


class AaidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.xml = Path(self.tmp.name) / 'page.xml'
        self.xml.write_text('<hierarchy><node class="android.widget.Button" text="one"/><node class="android.widget.Button" text="two"/></hierarchy>')
        self.page = PageSession(self.xml)

    def test_update_lookup_and_reassignment(self):
        self.assertIsNone(self.page.call('update_aaid', {'id': 1, 'value': '12'}))
        node = self.page.call('select_aaid', {'aaid': 12})
        self.assertEqual(node, self.page.call('page_node', {'key': 1}))
        self.assertEqual(node['aaid'], '12')
        self.page.update_aaid(1, '12')
        self.page.update_aaid(1, '-2')
        with self.assertRaises(ValueError):
            self.page.select_aaid(12)
        self.assertEqual(self.page.select_aaid(-2)['id'], 1)
        self.page.update_aaid(2, '12')
        self.assertEqual(self.page.select_aaid(12)['id'], 2)

    def test_duplicate_and_invalid_updates_are_atomic(self):
        self.page.update_aaid(0, '0')
        self.page.update_aaid(1, '1')
        for id, value in [(1, '0'), (999, '1'), (True, '1'), (1, 4)]:
            with self.assertRaises(ValueError):
                self.page.update_aaid(id, value)
        self.assertEqual(self.page.select_aaid(0)['id'], 0)
        self.assertEqual(self.page.select_aaid(1)['id'], 1)
        for name, args in [('update_aaid', {'id': 1}), ('select_aaid', {}),
                           ('select_aaid', {'aaid': '1'}), ('select_aaid', {'aaid': True})]:
            with self.assertRaises(ValueError):
                self.page.call(name, args)

    def test_string_values_and_session_lifetime(self):
        self.page.update_aaid(1, 'label')
        self.assertEqual(self.page.call('page_node', {'key': 1})['aaid'], 'label')
        with self.assertRaises(ValueError):
            self.page.select_aaid(1)
        self.page.update_aaid(1, '12')
        other = PageSession(self.xml)
        with self.assertRaises(ValueError):
            other.select_aaid(12)
        out = Path(self.tmp.name) / 'bundle'
        self.page.save(out)
        restored = PageSession.load(out)
        self.assertNotIn('aaid', restored.call('page_node', {'key': 1}))
