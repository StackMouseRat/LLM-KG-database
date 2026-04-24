# Nebula HTTP 网关（FastGPT 可调用）

## 0. Docker 集成（推荐）

`nebula-docker-compose/docker-compose-lite.yaml` 已集成 `nebula-http-gateway` 服务。

直接启动：

```powershell
docker compose -f nebula-docker-compose/docker-compose-lite.yaml up -d --build
```

启动后：
- 宿主机访问：`http://127.0.0.1:8787`
- FastGPT 容器内访问：`http://nebula-http-gateway:8787`

## 1. 启动网关

在项目根目录执行：

```powershell
python scripts/nebula_http_gateway.py --host 0.0.0.0 --port 8787
```

如果你的 Nebula 不在默认网络/主机，按需覆盖：

```powershell
python scripts/nebula_http_gateway.py `
  --host 0.0.0.0 `
  --port 8787 `
  --docker-network nebula-docker-compose_nebula-net `
  --nebula-host graphd `
  --nebula-port 9669 `
  --nebula-user root `
  --nebula-password nebula
```

## 2. 健康检查

```bash
curl -X GET "http://127.0.0.1:8787/graph/health"
```

## 3. 执行查询

```bash
curl -X POST "http://127.0.0.1:8787/graph/query" \
  -H "Content-Type: application/json" \
  -d "{\"space\":\"llmkg_test\",\"ngql\":\"GO FROM \\\"dev_cb_001\\\" OVER has_fault YIELD dst(edge) AS fault_id, has_fault.fault_time AS fault_time, has_fault.severity AS severity;\"}"
```

## 4. FastGPT HTTP 节点配置

- Method: `POST`
- URL（推荐，同网络容器直连）: `http://nebula-http-gateway:8787/graph/query`
- URL（备选，走宿主机映射）: `http://host.docker.internal:8787/graph/query`
- Headers: `Content-Type: application/json`
- Body(JSON):

```json
{
  "space": "llmkg_test",
  "ngql": "SHOW TAGS;"
}
```

说明：
- 网关返回字段 `ok=true` 表示查询成功。
- 原始查询输出在 `stdout` 字段中。

## 5. 本项目 Nebula 查询速查

本项目的设备故障图谱以多个 Nebula Space 分设备存放。当前常用 Space 包括：

- `llmkg_breaker`：断路器
- `llmkg_cable`：电力电缆
- `llmkg_mutual`：互感器
- `llmkg_optical_cable`：光缆
- `llmkg_ring_main_unit`：环网柜
- `llmkg_surge_arrester`：避雷器
- `llmkg_tower`：杆塔
- `llmkg_transformer`：变压器
- `llmkg_transmission_line`：输电线路
- `llmkg_test`：测试/历史验证空间

### 5.1 查询基本原则

- 优先从 Nebula 数据库读取设备、故障层级和关系，不以脚本或中间文件作为最终依据。
- 查询得到候选故障后，应回到对应原文或案例文本人工阅读，按语义判断相似故障；不要只做关键词或字符串完全匹配。
- 跨设备事故分析时，先查相关设备 Space 的一、二级故障，再结合事故原文梳理“起因—保护动作—设备跳闸—系统状态变化—事故扩大”的链条。
- 如果 Nebula 中缺少“稳控系统、继电保护、机组 OPC”等非一次设备实体，应在分析中标注为“当前设备图谱缺口/外部系统环节”。

### 5.2 常用检查命令

健康检查：

```bash
curl -sS "http://127.0.0.1:8787/graph/health"
```

查看全部 Space：

```bash
curl -sS -X POST "http://127.0.0.1:8787/graph/query" \
  -H "Content-Type: application/json" \
  -d '{"space":"llmkg_test","ngql":"SHOW SPACES;"}'
```

查看某个 Space 的标签和边类型：

```bash
curl -sS -X POST "http://127.0.0.1:8787/graph/query" \
  -H "Content-Type: application/json" \
  -d '{"space":"llmkg_breaker","ngql":"SHOW TAGS; SHOW EDGES;"}'
```

查看标签或边的字段定义：

```bash
curl -sS -X POST "http://127.0.0.1:8787/graph/query" \
  -H "Content-Type: application/json" \
  -d '{"space":"llmkg_breaker","ngql":"DESCRIBE TAG entity; DESCRIBE EDGE contains;"}'
```

### 5.3 典型查询流程

1. 选择设备对应 Space，例如断路器用 `llmkg_breaker`，输电线路用 `llmkg_transmission_line`。
2. 用 `SHOW TAGS; SHOW EDGES;` 确认当前 Space 的图模型。
3. 用 `DESCRIBE TAG ...` 和 `DESCRIBE EDGE ...` 确认点、边属性名。
4. 查询设备节点及其一、二级故障节点。
5. 根据故障节点名称、描述、上下游关系，人工挑选与事故原文语义相近的故障。
6. 回到原文资料或案例库，阅读相似故障上下文，再输出事故连锁分析。

### 5.4 当前事故分析建议查询范围

针对“一起电网瓦解事故”这类跨设备、跨保护系统事故，建议至少查询：

- `llmkg_transmission_line`：外力破坏、短路、断线、跳闸类故障。
- `llmkg_optical_cable`：光缆外力损坏、通信中断、保护通道异常类故障。
- `llmkg_breaker`：保护误动/拒动、跳闸、开断、控制回路类故障。
- `llmkg_transformer`：短路冲击、过负荷、低电压/厂用电异常导致的运行异常。
- `llmkg_mutual`：电压/电流测量异常、二次回路异常、保护测量输入异常。

稳控系统、省调稳控、发电机 OPC、低周减载等环节如果未在设备图谱中建模，应作为系统保护与自动装置环节单独标注。
