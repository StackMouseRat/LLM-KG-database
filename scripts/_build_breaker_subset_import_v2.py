import pandas as pd
from pathlib import Path
from collections import defaultdict, deque

root = Path(r'D:/Graduate_test/dataset')

cands = sorted(
    [p for p in root.glob('xls/**/节点_nodes.xlsx') if '断路器' in str(p)],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
chosen_nodes = None
chosen_links = None
for n in cands:
    l = n.with_name('关系_links.xlsx')
    if l.exists():
        chosen_nodes = n
        chosen_links = l
        break
if chosen_nodes is None:
    raise SystemExit('No breaker xlsx pair found')

nodes = pd.read_excel(chosen_nodes)
links = pd.read_excel(chosen_links)

id_col, name_col = 'id', 'name'
root_rows = nodes[nodes[name_col] == '高压断路器']
root_id = int(root_rows.iloc[0][id_col]) if not root_rows.empty else int(nodes[id_col].min())

adj = defaultdict(list)
for _, r in links.iterrows():
    try:
        adj[int(r['from'])].append(int(r['to']))
    except Exception:
        pass

first_level = sorted(dict.fromkeys(adj.get(root_id, [])))
if len(first_level) < 2:
    raise SystemExit('Not enough L1 faults')
selected_l1 = first_level[:2]

selected = {root_id}
for l1 in selected_l1:
    dq = deque([l1])
    while dq:
        u = dq.popleft()
        selected.add(u)
        for v in adj.get(u, []):
            if v not in selected:
                dq.append(v)

nodes_sub = nodes[nodes[id_col].astype(int).isin(selected)].copy()
links_sub = links[
    links['from'].astype(int).isin(selected) & links['to'].astype(int).isin(selected)
].copy()

level = {root_id: 0}
sub_adj = defaultdict(list)
for _, r in links_sub.iterrows():
    sub_adj[int(r['from'])].append(int(r['to']))

dq = deque([root_id])
while dq:
    u = dq.popleft()
    for v in sub_adj.get(u, []):
        if v not in level:
            level[v] = level[u] + 1
            dq.append(v)

def esc(s):
    if s is None:
        return ''
    s = str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')
    return s

def vid(i):
    return f'n_{int(i)}'

# DDL script
s1 = []
s1.append('DROP SPACE IF EXISTS llmkg_test;')
s1.append('CREATE SPACE IF NOT EXISTS llmkg_test(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));')
s1.append('USE llmkg_test;')
s1.append('CREATE TAG IF NOT EXISTS entity(name string, lvl int, source_id int);')
s1.append('CREATE EDGE IF NOT EXISTS rel(relation string);')

# DML script
s2 = []
s2.append('USE llmkg_test;')

vertex_records = []
for _, r in nodes_sub.sort_values(id_col).iterrows():
    nid = int(r[id_col])
    nm = esc(r.get('name', ''))
    lvl = int(level.get(nid, -1))
    vertex_records.append((vid(nid), nm, lvl, nid))

for i in range(0, len(vertex_records), 100):
    chunk = vertex_records[i:i+100]
    vals = ', '.join(f'"{a}":("{b}",{c},{d})' for a,b,c,d in chunk)
    s2.append('INSERT VERTEX entity(name, lvl, source_id) VALUES ' + vals + ';')

for i in range(0, len(links_sub), 120):
    ch = links_sub.sort_values('id').iloc[i:i+120]
    vals = []
    for _, r in ch.iterrows():
        f = vid(int(r['from']))
        t = vid(int(r['to']))
        rel = esc(r.get('relation', ''))
        vals.append(f'"{f}"->"{t}":("{rel}")')
    s2.append('INSERT EDGE rel(relation) VALUES ' + ', '.join(vals) + ';')

l1_vids = [vid(i) for i in selected_l1]
s2.append('FETCH PROP ON entity ' + ', '.join(f'"{x}"' for x in l1_vids) + ' YIELD properties(vertex).name AS name, properties(vertex).lvl AS lvl, properties(vertex).source_id AS source_id;')
s2.append('MATCH (v:entity) RETURN count(v) AS node_count;')
s2.append('MATCH ()-[e:rel]->() RETURN count(e) AS edge_count;')

p1 = root / 'nebula-docker-compose' / 'import_breaker_two_l1_step1_ddl.ngql'
p2 = root / 'nebula-docker-compose' / 'import_breaker_two_l1_step2_dml.ngql'
p1.write_text('\n'.join(s1), encoding='utf-8')
p2.write_text('\n'.join(s2), encoding='utf-8')

name_map = {int(r[id_col]): str(r[name_col]) for _, r in nodes_sub.iterrows()}
print({
    'chosen_nodes': str(chosen_nodes),
    'chosen_links': str(chosen_links),
    'selected_l1_ids': selected_l1,
    'selected_l1_names': [name_map.get(i,'') for i in selected_l1],
    'node_count': int(len(nodes_sub)),
    'edge_count': int(len(links_sub)),
    'step1': str(p1),
    'step2': str(p2),
})
