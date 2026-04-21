# 前端接口与类型定义

## 1. API 设计原则

前端不直接保存 FastGPT API key。

推荐链路：

```text
前端 -> 自建后端代理 -> FastGPT OpenAPI
```

如果为了本机答辩临时直连 FastGPT，必须确保 API key 不提交到仓库。

## 2. 生成预案接口

### 2.1 请求

```http
POST /api/plan/generate
Content-Type: application/json
```

```json
{
  "question": "暴雨导致电缆沟进水，开关柜出现绝缘告警，夜间值班，无法立即更换设备，需要一份双阶段预案。",
  "stream": true
}
```

### 2.2 响应

非流式 MVP 可先返回：

```json
{
  "answer": "1. 事件特征...",
  "trace": {
    "device": "llmkg_cable",
    "fault": "绝缘劣化与击穿故障",
    "graph": {
      "nodes": [],
      "edges": []
    },
    "rawDetail": {}
  }
}
```

## 3. TypeScript 类型

### 3.1 生成阶段

```ts
export type GenerateStage =
  | 'idle'
  | 'detecting_device'
  | 'querying_graph'
  | 'generating'
  | 'done'
  | 'error';
```

### 3.2 请求类型

```ts
export interface GeneratePlanRequest {
  question: string;
  stream?: boolean;
}
```

### 3.3 响应类型

```ts
export interface GeneratePlanResponse {
  answer: string;
  trace: PlanTrace;
}
```

### 3.4 溯源类型

```ts
export interface PlanTrace {
  device?: string;
  fault?: string;
  scene?: string;
  graph: TraceGraph;
  rawDetail?: unknown;
}
```

```ts
export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceEdge[];
}
```

```ts
export interface TraceNode {
  id: string;
  label: string;
  type:
    | 'root_node'
    | 'fault_l1'
    | 'fault_l2'
    | 'fault_cause'
    | 'fault_symptom'
    | 'response_measure'
    | 'fault_consequence'
    | 'safety_risk'
    | 'emergency_resource'
    | 'unknown';
  desc?: string;
  source?: 'KG' | 'GEN';
}
```

```ts
export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  label:
    | 'has_fault_category'
    | 'contains'
    | 'caused_by'
    | 'has_symptom'
    | 'handled_by'
    | 'results_in'
    | 'has_risk'
    | 'needs_resource'
    | string;
}
```

## 4. FastGPT 原始响应解析

FastGPT 调用时建议使用：

```json
{
  "stream": false,
  "detail": true,
  "messages": [
    {
      "role": "user",
      "content": "..."
    }
  ]
}
```

`detail=true` 会返回 `responseData`，其中可解析：

- `设备识别`
- `故障类型分析`
- `基础数据获取`
- `下游节点获取`
- `下游节点数据清洗`
- `最终生成`

## 5. 溯源解析建议

### 5.1 设备识别

从模块名为 `设备识别` 的节点中读取：

```ts
extractResult['设备表']
```

### 5.2 故障识别

从模块名为 `故障类型分析` 的节点中读取：

```ts
extractResult['故障二级节点']
```

### 5.3 图谱详情

从模块名为 `下游节点获取` 的 HTTP 节点中读取：

```ts
httpResult.stdout
```

解析 Nebula 表格，抽取：

- `name`
- `node_desc`
- `lvl`

### 5.4 图谱节点类型推断

可根据名称后缀推断：

```ts
function inferNodeType(name: string): TraceNode['type'] {
  if (name.endsWith('-故障原因')) return 'fault_cause';
  if (name.endsWith('-故障现象')) return 'fault_symptom';
  if (name.endsWith('-应对措施')) return 'response_measure';
  if (name.endsWith('-故障后果')) return 'fault_consequence';
  if (name.endsWith('-安全风险')) return 'safety_risk';
  if (name.endsWith('-应急资源')) return 'emergency_resource';
  return 'fault_l2';
}
```

## 6. 来源标记解析

最终方案文本中会包含：

- `[KG]`
- `[GEN]`

前端展示建议：

- `[KG]` 高亮为蓝色，表示来自知识图谱
- `[GEN]` 高亮为橙色，表示模型根据场景补全

## 7. 错误类型

```ts
export interface ApiError {
  message: string;
  type:
    | 'fastgpt_error'
    | 'nebula_error'
    | 'network_error'
    | 'empty_result'
    | 'unknown';
}
```

## 8. 最小后端代理接口

如果实现后端代理，推荐接口：

```http
POST /api/plan/generate
```

后端代理负责：

- 读取服务端环境变量中的 FastGPT API key
- 调用 FastGPT
- 返回 `answer + trace`
- 避免 API key 暴露到前端

