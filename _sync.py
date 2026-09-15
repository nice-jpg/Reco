"""Positional, type-based DFS reconciliation of public region trees."""
from copy import deepcopy
from itertools import zip_longest


def reconcile(old, new):
    if old is new:
        raise ValueError('old and new must be separate trees')
    bundle = deepcopy(new.bundle)
    before, after = old.bundle.presentation, bundle.presentation
    mapping, ratios, changes, deleted = {}, {}, [], {}
    next_id = old._next_id

    def size(p, key):
        return 1 + p.descendant_counts[key]

    def attrs(p, key):
        # Compare locally owned evidence only; descendant summaries would mark
        # every ancestor changed and incorrectly promote the LCA to the root.
        return [dict(p.nodes[source]['attributes']) for source in p.regions[key]['sources']]

    def remove(key, reason):
        r = before.regions[key]
        deleted[key] = {'code': 'node_deleted', 'id': key, 'reason': reason}
        if 'aaid' in r:
            deleted[key]['aaid'] = r['aaid']
        for child in r['children']:
            remove(child, reason)

    def insert(key):
        nonlocal next_id
        mapping[key] = next_id
        ratios[next_id] = 1.0
        next_id += 1
        after.regions[key].pop('aaid', None)
        for child in after.regions[key]['children']:
            insert(child)

    def visit(a, b, parent):
        if a is None:
            insert(b)
            changes.append({'kind': 'added', 'id': mapping[b]})
            return size(after, b)
        if b is None:
            remove(a, 'removed')
            changes.append({'kind': 'removed', 'id': a, 'anchor': parent})
            return size(before, a)
        if before.details(a)['type'] != after.details(b)['type']:
            remove(a, 'type_changed')
            insert(b)
            changes.append({'kind': 'replaced', 'id': mapping[b], 'old_id': a})
            return max(size(before, a), size(after, b))
        mapping[b] = a
        after.regions[b].pop('aaid', None)
        if 'aaid' in before.regions[a]:
            after.regions[b]['aaid'] = before.regions[a]['aaid']
        changed = attrs(before, a) != attrs(after, b) or before.regions[a]['bounds'] != after.regions[b]['bounds'] or before.regions[a]['state'] != after.regions[b]['state']
        count = int(changed)
        if changed:
            changes.append({'kind': 'updated', 'id': a})
        for ca, cb in zip_longest(before.regions[a]['children'], after.regions[b]['children']):
            count += visit(ca, cb, a)
        ratios[a] = min(1.0, count / size(before, a))
        return count

    visit(0, 0, None)
    after.regions = {mapping[k]: {**r, 'children': [mapping[c] for c in r['children']]}
                     for k, r in after.regions.items()}
    after.owner = {source: mapping[k] for source, k in after.owner.items()}
    for name in ('members', 'descendant_counts', '_entries'):
        setattr(after, name, {mapping[k]: value for k, value in getattr(after, name).items()})
    parents = {c: k for k, r in after.regions.items() for c in r['children']}
    anchors = [c.get('anchor') if c['kind'] == 'removed' else c['id'] for c in changes]
    def path(key):
        result = [key]
        while key in parents:
            key = parents[key]
            result.append(key)
        return result[::-1]
    common = path(anchors[0]) if anchors else []
    for anchor in anchors[1:]:
        other = path(anchor)
        length = 0
        for left, right in zip(common, other):
            if left != right:
                break
            length += 1
        common = common[:length]
    change_root = common[-1] if common else None
    # Commit only after the full reconciliation succeeds.
    tombstones = {**old._deleted_ids, **deleted}
    alias_errors = dict(old._deleted_aaids)
    for report in deleted.values():
        if 'aaid' in report:
            alias_errors[report['aaid']] = report
    old._bind(bundle)
    old._next_id = next_id
    old._deleted_ids = tombstones
    old._deleted_aaids = alias_errors
    old._update_ratios = ratios
    old._aaid_to_id = {r['aaid']: k for k, r in after.regions.items() if 'aaid' in r}
    old.last_changes = changes
    old.last_change_root = change_root
    return bundle.node(change_root) if change_root is not None else None
