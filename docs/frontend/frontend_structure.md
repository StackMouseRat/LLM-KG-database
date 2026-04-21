# 前端目录结构建议

## 1. 推荐目录结构

```text
frontend/
├── Dockerfile
├── nginx.conf
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── styles/
│   │   ├── global.css
│   │   └── theme.ts
│   ├── services/
│   │   └── planApi.ts
│   ├── types/
│   │   └── plan.ts
│   ├── utils/
│   │   ├── download.ts
│   │   ├── parseTrace.ts
│   │   └── graphTransform.ts
│   ├── components/
│   │   ├── AppShell.tsx
│   │   ├── StatusSteps.tsx
│   │   ├── MarkdownResult.tsx
│   │   ├── SourceTagLegend.tsx
│   │   └── ErrorPanel.tsx
│   └── pages/
│       ├── PlanGeneratePage.tsx
│       └── TraceGraphPage.tsx
```

## 2. 页面划分

### 2.1 `PlanGeneratePage`

职责：

- 输入故障场景
- 发起生成请求
- 展示生成状态
- 展示预案内容
- 提供复制、下载、查看溯源功能

主要状态：

```ts
const [question, setQuestion] = useState('');
const [loading, setLoading] = useState(false);
const [stage, setStage] = useState<GenerateStage>('idle');
const [answer, setAnswer] = useState('');
const [trace, setTrace] = useState<PlanTrace | null>(null);
const [error, setError] = useState<string | null>(null);
```

### 2.2 `TraceGraphPage`

职责：

- 展示知识图谱溯源
- 展示节点详情
- 展示本次生成的设备识别和故障识别结果

主要状态：

```ts
const [selectedNode, setSelectedNode] = useState<TraceNode | null>(null);
```

## 3. 核心组件

### 3.1 `AppShell`

负责整体布局：

- 顶部标题
- Tab 页签
- 页面容器

### 3.2 `StatusSteps`

展示阶段状态：

- `正在识别设备`
- `正在查询知识图谱`
- `正在生成预案`
- `生成完成`

不显示虚假百分比。

### 3.3 `MarkdownResult`

职责：

- 展示生成方案
- 高亮 `[KG]`
- 高亮 `[GEN]`

建议颜色：

- `[KG]`：蓝色
- `[GEN]`：橙色

### 3.4 `TraceGraphPage`

使用 G6 展示图谱：

- 节点颜色按类型区分
- 点击节点显示详情
- 支持缩放、拖拽

### 3.5 `SourceTagLegend`

展示来源标记含义：

- `[KG]`：来自知识图谱
- `[GEN]`：模型根据场景补全

## 4. 图谱可视化节点样式

建议节点类型与颜色：

```ts
const nodeColorMap = {
  fault_l2: '#2563eb',
  fault_cause: '#f97316',
  fault_symptom: '#0ea5e9',
  response_measure: '#22c55e',
  fault_consequence: '#ef4444',
  safety_risk: '#7c3aed',
  emergency_resource: '#14b8a6'
};
```

## 5. 路由策略

MVP 不需要路由，直接使用 Ant Design Tabs 即可。

如果后续扩展：

- `/generate`
- `/trace`
- `/settings`

## 6. Docker 部署

### 6.1 Dockerfile

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 6.2 nginx 代理建议

如果前端需要调用后端代理：

```nginx
location /api/ {
  proxy_pass http://backend:3001/;
}
```

不要把 FastGPT API key 写入前端静态文件。

