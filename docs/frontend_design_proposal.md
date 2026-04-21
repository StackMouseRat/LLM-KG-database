# 电力设备故障预案生成系统 - 前端设计方案

## 项目概述

基于现有的 FastGPT + Nebula 图数据库架构，构建一个面向一线运维人员的故障预案生成与管理系统。

## 核心功能需求

### 1. 预案生成
- 用户输入故障描述
- 调用 FastGPT API 生成结构化预案
- 实时显示生成进度
- 支持流式输出（stream mode）

### 2. 模板可视化编辑
- 可视化展示预案模板结构
- 拖拽式编辑模板字段
- 实时预览模板效果
- 支持自定义字段和格式

### 3. 输出可溯源
- 显示预案生成的数据来源
- 追溯到 Nebula 图数据库的具体节点
- 展示推理路径和依据
- 支持点击查看原始数据

## 技术架构设计

### 前端技术栈推荐

#### 方案A：React + Ant Design Pro（推荐）
```
- React 18 + TypeScript
- Ant Design / Ant Design Pro（企业级UI组件）
- React Flow（流程图/知识图谱可视化）
- Zustand / Redux（状态管理）
- React Query（API请求管理）
- Vite（构建工具）
```

**优势**：
- Ant Design Pro 提供开箱即用的企业级模板
- React Flow 适合展示工作流和溯源路径
- 生态成熟，组件丰富

#### 方案B：Vue 3 + Element Plus
```
- Vue 3 + TypeScript
- Element Plus（UI组件库）
- VueFlow（流程图可视化）
- Pinia（状态管理）
- Vite
```

**优势**：
- 学习曲线平缓
- Element Plus 适合后台管理系统
- Vue 3 性能优秀

### 后端API设计

#### 1. FastGPT API 集成
```typescript
// 预案生成接口
POST http://localhost:3000/api/v1/chat/completions
Headers:
  Authorization: Bearer {app-api-key}
  Content-Type: application/json

Body:
{
  "chatId": "unique-chat-id",
  "stream": true,  // 流式输出
  "detail": true,  // 获取详细执行信息
  "messages": [
    {
      "role": "user",
      "content": "电力电缆绝缘劣化与击穿故障的原因、现象和应对措施是什么？"
    }
  ]
}

Response (detail=true):
{
  "choices": [...],
  "responseData": [
    {
      "moduleName": "基础数据获取",
      "moduleType": "httpRequest468",
      "runningTime": 1.2,
      "query": "MATCH (l1:fault_l1)...",
      "response": {...}
    },
    ...
  ]
}
```

#### 2. 自定义中间层API（可选）
```typescript
// 如果需要更多控制，可以构建中间层
POST /api/plan/generate
{
  "faultDescription": "绝缘击穿",
  "deviceType": "breaker",
  "templateId": "template-001"
}

GET /api/plan/trace/{planId}
// 返回预案的完整溯源信息

POST /api/template/update
// 更新模板配置
```

## 页面设计

### 1. 预案生成页面

```
┌─────────────────────────────────────────────────┐
│  故障预案生成系统                                │
├─────────────────────────────────────────────────┤
│                                                 │
│  设备类型: [断路器 ▼]  模板: [标准预案 ▼]      │
│                                                 │
│  故障描述:                                       │
│  ┌───────────────────────────────────────────┐ │
│  │ 电力电缆绝缘劣化与击穿故障              │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  [生成预案] [清空] [历史记录]                   │
│                                                 │
├─────────────────────────────────────────────────┤
│  生成结果:                                       │
│  ┌───────────────────────────────────────────┐ │
│  │ 当前故障设备是电力电缆                   │ │
│  │                                           │ │
│  │ 【故障判断】                              │ │
│  │ - 绝缘劣化导致击穿故障 [溯源🔍]          │ │
│  │                                           │ │
│  │ 【判断依据】                              │ │
│  │ 1. 绝缘老化... [查看来源]                │ │
│  │ 2. 环境因素... [查看来源]                │ │
│  │                                           │ │
│  │ 【处理建议】                              │ │
│  │ ...                                       │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  [导出PDF] [导出Word] [保存草稿] [查看溯源]    │
└─────────────────────────────────────────────────┘
```

### 2. 模板编辑页面

```
┌─────────────────────────────────────────────────┐
│  预案模板编辑器                                  │
├─────────────────────────────────────────────────┤
│  模板名称: [标准预案模板]                       │
│  适用设备: [断路器] [输电线] [变压器]           │
│                                                 │
│  ┌─────────────┬─────────────────────────────┐ │
│  │ 模板结构    │  字段配置                   │ │
│  ├─────────────┼─────────────────────────────┤ │
│  │ □ 故障判断  │  显示名称: 故障判断         │ │
│  │ □ 判断依据  │  是否必填: ☑               │ │
│  │ □ 处理建议  │  最小条目: 2               │ │
│  │ □ 风险提示  │  最大条目: 4               │ │
│  │ □ 应急资源  │  提示词模板:               │ │
│  │             │  ┌─────────────────────┐   │ │
│  │ [+添加字段] │  │ 必须给出2~4条依据   │   │ │
│  │             │  │ 并引用检索结果...   │   │ │
│  │             │  └─────────────────────┘   │ │
│  └─────────────┴─────────────────────────────┘ │
│                                                 │
│  [保存模板] [预览] [测试生成] [版本历史]        │
└─────────────────────────────────────────────────┘
```

### 3. 溯源可视化页面

```
┌─────────────────────────────────────────────────┐
│  预案溯源分析                                    │
├─────────────────────────────────────────────────┤
│  预案ID: plan-20260421-001                      │
│  生成时间: 2026-04-21 14:30:25                  │
│                                                 │
│  执行流程:                                       │
│  ┌───────────────────────────────────────────┐ │
│  │                                           │ │
│  │  [用户输入] → [设备识别] → [故障分类]    │ │
│  │       ↓            ↓            ↓         │ │
│  │  "绝缘击穿"   llmkg_breaker  "绝缘劣化"  │ │
│  │                                           │ │
│  │  → [基础数据查询] → [下游节点查询]       │ │
│  │         ↓                 ↓               │ │
│  │    34条映射          6类信息              │ │
│  │                                           │ │
│  │  → [AI生成] → [输出预案]                 │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  数据来源详情:                                   │
│  ┌───────────────────────────────────────────┐ │
│  │ 节点: fault_l2.绝缘劣化                  │ │
│  │ 查询: MATCH (f:entity) WHERE...          │ │
│  │ 返回: 3个原因, 2个措施, 1个风险          │ │
│  │                                           │ │
│  │ [查看原始数据] [在图谱中查看]            │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  知识图谱可视化:                                 │
│  ┌───────────────────────────────────────────┐ │
│  │        ┌─────────┐                        │ │
│  │        │绝缘劣化 │                        │ │
│  │        └────┬────┘                        │ │
│  │             │                             │ │
│  │    ┌────────┼────────┐                   │ │
│  │    ↓        ↓        ↓                   │ │
│  │  [原因]  [措施]  [后果]                  │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 核心功能实现

### 1. 预案生成（流式输出）

```typescript
// hooks/useStreamGeneration.ts
import { useState } from 'react';

export function useStreamGeneration() {
  const [content, setContent] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [traceData, setTraceData] = useState(null);

  const generate = async (faultDescription: string) => {
    setIsGenerating(true);
    setContent('');

    const response = await fetch('http://localhost:3000/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        chatId: `chat-${Date.now()}`,
        stream: true,
        detail: true,
        messages: [
          { role: 'user', content: faultDescription }
        ]
      })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(line => line.trim());

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          
          if (data.choices?.[0]?.delta?.content) {
            setContent(prev => prev + data.choices[0].delta.content);
          }

          if (data.responseData) {
            setTraceData(data.responseData);
          }
        }
      }
    }

    setIsGenerating(false);
  };

  return { content, isGenerating, traceData, generate };
}
```

### 2. 模板可视化编辑

```typescript
// components/TemplateEditor.tsx
import { Form, Input, Switch, InputNumber, Button } from 'antd';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

interface TemplateField {
  id: string;
  name: string;
  required: boolean;
  minItems?: number;
  maxItems?: number;
  promptTemplate: string;
}

export function TemplateEditor() {
  const [fields, setFields] = useState<TemplateField[]>([
    { id: '1', name: '故障判断', required: true, promptTemplate: '...' },
    { id: '2', name: '判断依据', required: true, minItems: 2, maxItems: 4, promptTemplate: '...' },
    // ...
  ]);

  const onDragEnd = (result) => {
    if (!result.destination) return;
    const items = Array.from(fields);
    const [reordered] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, reordered);
    setFields(items);
  };

  const saveTemplate = async () => {
    // 保存到 FastGPT 的 system prompt
    const systemPrompt = generateSystemPrompt(fields);
    
    // 通过数据库直改或 API 更新工作流
    await updateWorkflowPrompt(systemPrompt);
  };

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <Droppable droppableId="fields">
        {(provided) => (
          <div {...provided.droppableProps} ref={provided.innerRef}>
            {fields.map((field, index) => (
              <Draggable key={field.id} draggableId={field.id} index={index}>
                {(provided) => (
                  <div ref={provided.innerRef} {...provided.draggableProps} {...provided.dragHandleProps}>
                    <FieldEditor field={field} onChange={(updated) => updateField(index, updated)} />
                  </div>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>
  );
}
```

### 3. 溯源可视化

```typescript
// components/TraceVisualization.tsx
import ReactFlow, { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';

export function TraceVisualization({ traceData }) {
  const nodes: Node[] = traceData.map((step, index) => ({
    id: `step-${index}`,
    type: 'custom',
    position: { x: index * 200, y: 100 },
    data: {
      label: step.moduleName,
      type: step.moduleType,
      time: step.runningTime,
      query: step.query,
      response: step.response
    }
  }));

  const edges: Edge[] = nodes.slice(0, -1).map((node, index) => ({
    id: `edge-${index}`,
    source: node.id,
    target: `step-${index + 1}`,
    animated: true
  }));

  return (
    <div style={{ height: '400px' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={{ custom: CustomNode }}
        fitView
      />
    </div>
  );
}

function CustomNode({ data }) {
  return (
    <div className="custom-node">
      <div className="node-header">{data.label}</div>
      <div className="node-body">
        <div>类型: {data.type}</div>
        <div>耗时: {data.time}s</div>
        {data.query && (
          <Button size="small" onClick={() => showQueryDetail(data)}>
            查看查询
          </Button>
        )}
      </div>
    </div>
  );
}
```

## 参考项目

### 1. FastGPT 官方前端
- **仓库**: https://github.com/labring/FastGPT
- **技术栈**: Next.js + Chakra UI
- **可参考**:
  - 工作流编辑器实现
  - API 调用封装
  - 流式输出处理

### 2. Dify（开源LLM应用开发平台）
- **仓库**: https://github.com/langgenius/dify
- **技术栈**: React + TailwindCSS
- **可参考**:
  - 工作流可视化编辑
  - 提示词模板管理
  - 对话历史和溯源展示

### 3. Flowise（低代码LLM工作流）
- **仓库**: https://github.com/FlowiseAI/Flowise
- **技术栈**: React + ReactFlow
- **可参考**:
  - 节点拖拽编辑
  - 工作流执行可视化
  - 数据流追踪

### 4. LangFlow（可视化LLM链构建）
- **仓库**: https://github.com/logspace-ai/langflow
- **技术栈**: React + ReactFlow
- **可参考**:
  - 流程图编辑器
  - 组件配置面板
  - 实时预览

### 5. Ant Design Pro（企业级后台模板）
- **官网**: https://pro.ant.design/
- **可参考**:
  - 完整的后台管理系统架构
  - 权限管理
  - 表单和表格组件

## 实施建议

### 阶段一：MVP（2-3周）
1. 基础预案生成页面
2. 接入 FastGPT API
3. 简单的结果展示
4. 导出功能（PDF/Word）

### 阶段二：模板编辑（2-3周）
1. 模板列表管理
2. 可视化模板编辑器
3. 模板预览和测试
4. 版本管理

### 阶段三：溯源可视化（2-3周）
1. 执行流程可视化
2. 数据来源追踪
3. 知识图谱展示
4. 交互式探索

### 阶段四：优化增强（持续）
1. 性能优化
2. 用户体验优化
3. 移动端适配
4. 权限和多租户

## 技术难点与解决方案

### 1. 模板编辑如何同步到 FastGPT
**方案A**: 数据库直改（参考现有文档）
- 直接修改 MongoDB 中的 `apps.modules` 和 `app_versions`
- 需要理解 FastGPT 的数据结构

**方案B**: 通过 FastGPT API（如果支持）
- 调用 FastGPT 的管理 API
- 更安全，但可能功能受限

**推荐**: 方案A + 中间层封装，提供安全的模板更新接口

### 2. 溯源数据的获取
- 使用 `detail: true` 参数获取完整执行信息
- 解析 `responseData` 中的模块执行记录
- 提取 Nebula 查询语句和返回结果

### 3. 实时流式输出
- 使用 Server-Sent Events (SSE)
- 前端使用 EventSource 或 fetch + ReadableStream
- 处理断线重连

### 4. 知识图谱可视化
- 使用 ReactFlow 或 G6（AntV）
- 从 Nebula 查询结果构建图结构
- 支持节点点击查看详情

## 部署建议

### 开发环境
```bash
# 前端
cd frontend
npm install
npm run dev  # http://localhost:5173

# 后端（如果有中间层）
cd backend
npm install
npm run dev  # http://localhost:3001
```

### 生产环境
```bash
# 使用 Docker Compose
docker-compose up -d

# 或使用 Nginx 反向代理
# 前端静态文件 -> Nginx
# API 请求 -> FastGPT (localhost:3000)
```

## 安全考虑

1. **API Key 管理**
   - 不要在前端暴露 API Key
   - 通过后端中间层代理请求

2. **权限控制**
   - 用户认证和授权
   - 不同角色的功能权限

3. **数据验证**
   - 输入验证和清洗
   - 防止注入攻击

4. **审计日志**
   - 记录所有预案生成和模板修改操作
   - 便于追溯和问题排查

## 总结

这个前端项目的核心是：
1. **预案生成**: 调用 FastGPT API，流式展示结果
2. **模板编辑**: 可视化编辑系统提示词，同步到工作流
3. **溯源可视化**: 展示执行流程和数据来源

推荐使用 **React + Ant Design Pro + ReactFlow** 技术栈，参考 Dify 和 Flowise 的实现方式，分阶段开发，先实现 MVP，再逐步完善功能。
