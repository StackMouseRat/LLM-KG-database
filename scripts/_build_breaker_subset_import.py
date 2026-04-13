import pandas as pd
from pathlib import Path
from collections import defaultdict, deque

root = Path(r'D:/Graduate_test/dataset')
# choose latest nodes file that has sibling links file
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

id_col = 'id'
name_col = 'name'
if id_col not in nodes.columns or name_col not in nodes.columns:
    raise SystemExit('nodes file missing id/name columns')

root_rows = nodes[nodes[name_col] == '高压断路器']
if root_rows.empty:
    root_id = int(nodes[id_col].min())
else:
    root_id = int(root_rows.iloc[0][id_col])

# adjacency from links
adj = defaultdict(list)
for _, r in links.iterrows():
    try:
        f = int(r['from'])
        t = int(r['to'])
    except Exception:
        continue
    adj[f].append(t)

first_level = adj.get(root_id, [])
first_level = sorted(dict.fromkeys(first_level))
if len(first_level) < 2:
    raise SystemExit(f'Not enough first-level faults under root {root_id}')
selected_l1 = first_level[:2]

# collect descendants for each selected L1
selected = {root_id}
for l1 in selected_l1:
    dq = deque([l1])
    while dq:
        u = dq.popleft()
        if u in selected:
            pass
        selected.add(u)
        for v in adj.get(u, []):
            if v not in selected:
                dq.append(v)

# subgraph
nodes_sub = nodes[nodes[id_col].astype(int).isin(selected)].copy()
links_sub = links[
    links['from'].astype(int).isin(selected) & links['to'].astype(int).isin(selected)
].copy()

# compute level from root within subgraph
level = {root_id: 0}
dq = deque([root_id])
sub_adj = defaultdict(list)
for _, r in links_sub.iterrows():
    sub_adj[int(r['from'])].append(int(r['to']))
while dq:
    u = dq.popleft()
    for v in sub_adj.get(u, []):
        if v not in level:
            level[v] = level[u] + 1
            dq.append(v)

# helpers

def esc(s):
    if s is None:
        return ''
    s = str(s)
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')
    return s

def vid(i):
    return f'n_{int(i)}'

def as_int(v, default=0):
    try:
        if pd.isna(v):
            return default
        return int(v)
    except Exception:
        return default

ngql_lines = []
ngql_lines.append('DROP SPACE IF EXISTS llmkg_test;')
ngql_lines.append('CREATE SPACE IF NOT EXISTS llmkg_test(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));')
ngql_lines.append('USE llmkg_test;')
ngql_lines.append('CREATE TAG IF NOT EXISTS entity(name string, node_desc string, degree int, weight int, stroke string, lvl int, source_id int);')
ngql_lines.append('CREATE EDGE IF NOT EXISTS rel(relation string, from_name string, to_name string);')

# vertices in chunks
vertex_records = []
for _, r in nodes_sub.sort_values(id_col).iterrows():
    nid = as_int(r[id_col])
    rec = (
        vid(nid),
        esc(r.get('name', '')),
        esc(r.get('desc', '')),
        as_int(r.get('degree', 0)),
        as_int(r.get('weight', 0)),
        esc(r.get('stroke', '')),
        int(level.get(nid, -1)),
        nid,
    )
    vertex_records.append(rec)

for i in range(0, len(vertex_records), 80):
    chunk = vertex_records[i:i+80]
    vals = ', '.join(
        f'"{v[0]}":("{v[1]}","{v[2]}",{v[3]},{v[4]},"{v[5]}",{v[6]},{v[7]})' for v in chunk
    )
    ngql_lines.append('INSERT VERTEX entity(name, node_desc, degree, weight, stroke, lvl, source_id) VALUES ' + vals + ';')

# edges in chunks
edge_records = []
name_map = {as_int(r[id_col]): esc(r.get('name', '')) for _, r in nodes_sub.iterrows()}
for _, r in links_sub.sort_values('id').iterrows():
    f = as_int(r['from'])
    t = as_int(r['to'])
    edge_records.append((vid(f), vid(t), esc(r.get('relation', '')), esc(r.get('fromNodeName', name_map.get(f,''))), esc(r.get('toNodeName', name_map.get(t,'')))))

for i in range(0, len(edge_records), 120):
    chunk = edge_records[i:i+120]
    vals = ', '.join(
        f'"{e[0]}"->"{e[1]}":("{e[2]}","{e[3]}","{e[4]}")' for e in chunk
    )
    ngql_lines.append('INSERT EDGE rel(relation, from_name, to_name) VALUES ' + vals + ';')

# verification
l1_vids = [vid(i) for i in selected_l1]
ngql_lines.append('FETCH PROP ON entity ' + ', '.join(f'"{x}"' for x in l1_vids) + ' YIELD properties(vertex).name AS name, properties(vertex).lvl AS lvl, properties(vertex).source_id AS source_id;')
ngql_lines.append('GO FROM "' + vid(root_id) + '" OVER rel YIELD dst(edge) AS child, rel.relation AS relation, rel.to_name AS to_name;')
ngql_lines.append('MATCH (v:entity) RETURN count(v) AS node_count;')
ngql_lines.append('MATCH ()-[e:rel]->() RETURN count(e) AS edge_count;')

out = root / 'nebula-docker-compose' / 'import_breaker_two_l1.ngql'
out.write_text('\n'.join(ngql_lines), encoding='utf-8')

summary = {
    'chosen_nodes': str(chosen_nodes),
    'chosen_links': str(chosen_links),
    'root_id': root_id,
    'selected_l1_ids': selected_l1,
    'selected_l1_names': [name_map.get(i, '') for i in selected_l1],
    'node_count': int(len(nodes_sub)),
    'edge_count': int(len(links_sub)),
    'ngql_path': str(out),
}
print(summary)
