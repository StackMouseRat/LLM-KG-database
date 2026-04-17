# Nebula 初始化与分表说明

## 1. 目标
- 为多设备故障图谱建立独立 `space`，避免不同设备数据混杂。
- 统一每个 `space` 的 schema，便于工作流复用同一套查询模板。

## 2. 推荐分表（按设备分 space）
- `llmkg_breaker`（断路器）
- `llmkg_transformer`（变压器）
- `llmkg_transmission_line`（输电线路）
- `llmkg_mutual`（互感器）
- `llmkg_cable`（电缆）
- `llmkg_optical_cable`（光缆）
- `llmkg_ring_main_unit`（环网柜）
- `llmkg_surge_arrester`（避雷器）
- `llmkg_tower`（杆塔）
- `llmkg_test`（历史测试空间，可选保留）

## 3. 初始化步骤

### 3.1 启动服务
```powershell
docker compose -f nebula-docker-compose/docker-compose-lite.yaml up -d
```

### 3.2 健康检查（网关）
```powershell
curl http://127.0.0.1:18787/graph/health
```

### 3.3 创建 space
```ngql
CREATE SPACE IF NOT EXISTS llmkg_breaker(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_transformer(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_transmission_line(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_mutual(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_cable(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_optical_cable(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_ring_main_unit(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_surge_arrester(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_tower(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
CREATE SPACE IF NOT EXISTS llmkg_test(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));
```

### 3.4 每个 space 的统一 schema
对每个 space 执行一次（`USE <space>;` 后执行）：
```ngql
CREATE TAG IF NOT EXISTS entity(
  name string,
  node_desc string,
  lvl int,
  source_id int,
  degree int,
  weight int,
  stroke string
);
CREATE EDGE IF NOT EXISTS rel(relation string);
CREATE TAG INDEX IF NOT EXISTS entity_lvl_idx ON entity(lvl);
```

## 4. 导入策略（nodes/links）
- 输入文件：`节点_nodes.xlsx` + `关系_links.xlsx`
- 顶点映射：
  - `vid`: `"n_<id>"`
  - `name <- name`
  - `node_desc <- desc`
  - `source_id <- id`
  - `degree <- degree`
  - `weight <- weight`
  - `stroke <- stroke`
  - `lvl`: 由 `from->to` 图做 BFS 推断层级（根节点 `in_degree=0` 为 `lvl=0`）
- 边映射：
  - `"n_from"->"n_to":("relation")`
- 建议批量插入：
  - `INSERT VERTEX` 每批 5~20 条
  - `INSERT EDGE` 每批 10~40 条
- 注意先清洗文本中的控制字符/私有区字符，避免 502 或编码异常。

## 5. 推荐工作流路由
1. 第一个 LLM 节点先做“设备识别”（只输出 space 名称）。
2. 查询节点把输出 space 填入 HTTP body 的 `space` 字段。
3. 后续统一用该 space 的图查询模板。

示例：
```json
{
  "space": "llmkg_mutual",
  "ngql": "MATCH (v:entity) WHERE v.entity.lvl == 1 RETURN v.entity.source_id AS source_id, v.entity.name AS name ORDER BY source_id;"
}
```

## 6. 导入后校验
```ngql
SHOW SPACES;
SHOW TAGS;
SHOW EDGES;
MATCH (v:entity) RETURN count(v) AS c;
MATCH ()-[e:rel]->() RETURN count(e) AS c;
```

## 7. 当前已导入状态（本仓库当前）
- `llmkg_breaker`: `entity=246`, `rel=245`
- `llmkg_transmission_line`: `entity=190`, `rel=215`
- `llmkg_transformer`: `entity=71`, `rel=80`
- `llmkg_mutual`: `entity=73`, `rel=72`

其余 space 已创建但尚未导入对应设备数据时，查询会出现 `Unknown tag`（属于正常现象）。

