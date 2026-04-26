# 前端现状说明

## 文档目的

本文档用于同步 `frontend/` 目录当前已经落地的页面、交互能力、接口串接关系和实现边界，作为论文演示版前端的现状说明。

## 技术栈

- `React 19`
- `Vite`
- `Ant Design`
- `@antv/g6`

前端主代码位于 `frontend/src/`，本地代理位于 `frontend/server/proxy.mjs`。

## 当前已实现页面

### 1. 登录页 `/login`

- 支持用户名密码登录。
- 会请求 `/api/auth/me` 检查当前会话状态。
- 登录成功后跳转到 `/plan`。
- 已接入登出动作和基础登录失败提示。

### 2. 预案生成页 `/plan`

- 支持输入故障场景问题。
- 支持随机填充预置示例问题。
- 支持开启“案例搜索”。
- 支持开启“多故障检索”。
- 支持以流式方式展示章节生成结果。
- 支持展示模板名、章节数、故障标签等摘要信息。
- 支持复制全部章节结果。
- 支持下载全部结果为 Markdown。
- 支持将最近一次成功生成结果缓存到浏览器本地，便于刷新后恢复。

## 预案生成页的执行链路

前端调用 `/api/pipeline/run`，由 `frontend/server/proxy.mjs` 启动 `scripts/run_parallel_generation_pipeline.py`，并通过 SSE 向浏览器持续回传以下阶段事件：

- 基础信息提取
- 模板切分
- 并行章节生成
- 案例检索
- 完成或失败

章节结果会逐章流式写入页面，而不是等待整份预案一次性返回。

### 3. 图谱溯源页 `/trace`

- 基于最近一次成功生成的预案结果继续工作。
- 会从预案结果中读取设备与故障信息，再请求 `/api/trace/subgraph`。
- 使用 G6 绘制当前故障相关的图谱子图。
- 支持展示设备根节点、主故障节点、命中故障节点、节点数、边数和命中节点数。
- 支持点击节点查看选中节点信息。

### 4. 格式优化与质量评估页 `/quality`

- 基于最近一次成功生成的章节结果继续工作。
- 支持按章节执行：
  - 格式优化
  - 原文评估
  - 优化后评估
- 支持批量执行上述操作，并设置并发数。
- 处理结果采用流式展示。
- 处理过程中会先显示 reasoning，再切换为正式输出。
- 支持读取、缓存、编辑和保存质量评估相关提示词。

### 5. 模板查看页 `/template`

- 支持读取模板章节列表。
- 支持展示每个章节的 `section_id`、`section_no`、`title`、`level`、`source_type`、`kg_field`、`fixed_text`、`gen_instruction`。
- 管理员账号可编辑 `source_type`、`fixed_text`、`gen_instruction`。
- 管理员账号可保存单章配置，也可恢复默认值。
- 普通用户当前为只读模式。

## 当前权限模型

- 前端已经区分 `admin` 和 `user` 两类用户组。
- `admin` 可以编辑模板章节和质量评估提示词。
- `user` 只能查看相关内容，不能保存或恢复默认配置。

## 当前串接的接口能力

### 已在代码中直接确认的接口

- `/api/auth/me`
- `/api/auth/login`
- `/api/auth/logout`
- `/api/pipeline/run`
- `/api/trace/subgraph`
- `/api/quality/review`
- `/api/template/sections`
- `/api/template/section/save`
- `/api/template/section/reset`
- `/api/template/prompts`
- `/api/template/prompt/save`

### 已在仓库中直接确认的本地代理

- `frontend/server/proxy.mjs` 已明确实现 `/api/pipeline/run` 的本地代理，并调用 `scripts/run_parallel_generation_pipeline.py`。

### 当前边界

- 其余接口虽然已经在前端代码中接入，但服务端实现不全部位于本仓库中。
- 这意味着当前仓库可以明确证明“前端已按这些接口完成集成”，但不能仅凭 `frontend/` 目录断言所有后端服务都在本仓库内独立闭环。

## 当前未固化的能力

- 历史记录列表与多次运行管理
- 预案正文在线编辑
- 多人协作
- 完整移动端适配
- 更细粒度的工作流调试与执行路径可视化

## 相关代码位置

- `frontend/src/App.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/TraceGraphPage.tsx`
- `frontend/src/pages/QualityReviewPage.tsx`
- `frontend/src/pages/TemplateViewPage.tsx`
- `frontend/src/services/authApi.ts`
- `frontend/src/services/planApi.ts`
- `frontend/server/proxy.mjs`
