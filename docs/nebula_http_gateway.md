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
