from pathlib import Path
import tempfile
import unittest
from .. import build_tree, sync


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.number = 0

    def tree(self, text='first', kind='Button', extra='', bounds='[0,0][100,100]'):
        self.number += 1
        p = Path(self.tmp.name) / f'{self.number}.xml'
        p.write_text(f'<hierarchy><node class="android.widget.ScrollView" bounds="[0,0][100,300]"><node class="android.widget.{kind}" text="{text}" bounds="{bounds}"/>{extra}</node></hierarchy>')
        return build_tree(p)

    def test_noop_and_attribute_update_preserve_alias_and_minimal_root(self):
        old = self.tree()
        old.update_aaid(2, '12')
        new = self.tree()
        self.assertIsNone(sync(old, new))
        self.assertEqual(old.update_ratio(0), 0)
        self.assertEqual(old.select_aaid(12)['id'], 2)
        changed = self.tree(text='scrolled', bounds='[0,-20][100,80]')
        result = sync(old, changed)
        self.assertEqual(result['id'], 2)
        self.assertEqual(old.last_change_root, 2)
        self.assertEqual(old.select_aaid(12)['bounds'], [0,-20,100,80])
        self.assertEqual(old.update_ratio(2), 1)
        self.assertEqual(old.update_ratio(1), .5)
        self.assertAlmostEqual(old.call('update_ratio', {'id': 0}), 1/3)
        self.assertEqual(changed.bundle.node(2).get('aaid'), None)
        self.assertIsNone(sync(old, self.tree(text='scrolled', bounds='[0,-20][100,80]')))
        self.assertEqual(old.update_ratio(2), 0)

    def test_type_replacement_deletes_alias_and_never_reuses_id(self):
        old = self.tree()
        old.update_aaid(2, '12')
        result = sync(old, self.tree(kind='ImageView'))
        self.assertEqual(result['id'], 3)
        self.assertNotIn('aaid', result)
        self.assertEqual(old.update_ratio(2), 1)
        error = old.select_aaid(12)
        self.assertIsNone(error['node'])
        self.assertEqual(error['error']['reason'], 'type_changed')
        sync(old, self.tree(kind='Button'))
        self.assertEqual(old.bundle.view(1)['regions'][0]['id'], 4)
        self.assertEqual(old.update_ratio(2), 1)
        self.assertEqual(old.update_ratio(3), 1)
        self.assertEqual(old.bundle.read(4)['entries'][0]['value'], 'first')

    def test_removal_lca_and_insertion_ratios(self):
        extra='<node class="android.widget.Button" text="second"/>'
        old=self.tree(extra=extra)
        old.update_aaid(3,'9')
        result=sync(old,self.tree())
        self.assertEqual(result['id'],1)
        self.assertEqual(old.update_ratio(1),1/3)
        self.assertEqual(old.select_aaid(9)['error']['reason'],'removed')
        result=sync(old,self.tree(text='updated',extra=extra*5))
        self.assertEqual(result['id'],1)
        self.assertEqual(old.update_ratio(1),1)
        self.assertEqual(old.bundle.view(1)['sub-regions'],6)
        self.assertTrue(all(c['id']!=3 for c in old.bundle.view(1)['regions']))

    def test_replaced_parent_drops_all_descendant_aliases(self):
        old=self.tree()
        old.update_aaid(1,'1');old.update_aaid(2,'2')
        new=self.tree()
        # Construct an XML with another actionable container type.
        p=Path(self.tmp.name)/'parent.xml'
        p.write_text('<hierarchy><node class="android.view.ViewGroup" clickable="true" bounds="[0,0][100,300]"><node class="android.widget.Button" text="first"/></node></hierarchy>')
        result=sync(old,build_tree(p))
        self.assertEqual(result['id'],3)
        self.assertIsNone(old.select_aaid(1)['node'])
        self.assertIsNone(old.select_aaid(2)['node'])
        self.assertEqual(old.bundle.view(3)['regions'][0]['id'],4)

    def test_unknown_ids_and_independent_sessions(self):
        old=self.tree();other=self.tree()
        with self.assertRaises(ValueError):old.update_ratio(999)
        with self.assertRaises(ValueError):old.update_ratio(True)
        with self.assertRaises(ValueError):sync(old,old)
        self.assertEqual(other.update_ratio(0),0)

    def test_real_scroll_sequences_keep_queries_consistent(self):
        from .test_page_tree import EXAMPLES
        for directory in sorted((EXAMPLES / 'scrolls').iterdir()):
            files=sorted(directory.glob('*.xml'))
            if not files:continue
            current=build_tree(files[0])
            for key in current.bundle.presentation.regions:
                current.update_aaid(key,str(key))
            for file in files[1:]:
                fresh=build_tree(file)
                sync(current,fresh)
                def compare(a,b):
                    left=current.bundle.node(a);right=fresh.bundle.node(b)
                    left.pop('id');left.pop('aaid',None);right.pop('id')
                    self.assertEqual(left,right,str(file))
                    self.assertEqual(current.bundle.read(a)['entries'],fresh.bundle.read(b)['entries'])
                    self.assertTrue(0<=current.update_ratio(a)<=1)
                    ca=current.bundle.presentation.regions[a]['children']
                    cb=fresh.bundle.presentation.regions[b]['children']
                    self.assertEqual(len(ca),len(cb))
                    for x,y in zip(ca,cb):compare(x,y)
                compare(0,0)
                for alias,key in current._aaid_to_id.items():
                    self.assertEqual(current.select_aaid(int(alias)),current.bundle.node(key))
