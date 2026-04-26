# 基于大模型与知识图谱的电气设备应急预案智能生成

本项目是一个面向电力设备故障场景的研究型原型仓库，目标是把设备故障资料整理为可复用的知识图谱、检索知识库和图查询工作流，用于支撑故障问答、风险说明和应急预案生成。仓库当前已经形成从原始资料整理、图谱建模、Nebula 导入、FastGPT 工作流编排到原型联调的完整链路。

## 项目定位

- 面向课题“基于大模型与知识图谱的电气设备应急预案智能生成方法”的实验与工程落地。
- 重点不是单一 Web 应用，而是“数据资产 + 图谱资产 + 查询链路 + 工作流配置”的一体化工程。
- 当前主要依赖 `NebulaGraph + HTTP 网关 + FastGPT` 完成图查询和回答生成。

## 当前进度

### 已完成

- 已完成多类设备的故障层级梳理文本，仓库中已覆盖断路器、输电线路、变压器、互感器、光缆、环网柜等设备方向。
- 已形成多套可导入 NRD Studio/图谱工具的 Excel 成品，位于 `xls/成品/`。
- 已完成断路器、输电线两类设备的 FastGPT 知识库导入包整理，包含结构化 CSV、上传 TXT、检索配置和槽位 schema。
- 已完成 Nebula 图数据库的导入、索引与校验脚本沉淀，断路器图谱导入链路已验证可复现。
- 已打通 FastGPT 通过 HTTP 节点调用 Nebula 查询的原型链路。
- 已形成论文演示版前端，支持登录、预案生成、图谱溯源、模板查看以及格式优化与质量评估。

### 正在推进

- 正在把单设备验证流程扩展为多设备统一入口工作流。
- 正在补齐光缆、环网柜等新设备的图谱自动生成脚本与成品资产。
- 正在进行案例验证、生成稳定性优化和量化评测设计。

### 当前阶段判断

- 第一阶段：资料整理与模板结构设计，已完成。
- 第二阶段：知识图谱本体与结构化资产构建，已完成。
- 第三阶段：FastGPT 工作流与图查询链路，已完成可运行版本。
- 第四阶段：原型联调、案例验证、评测与论文实验，进行中。

## 当前工作流流程

当前以 `frontend/` 中的前端实现作为工作流事实来源，不再以仓库中的历史 FastGPT JSON 导出文件作为主说明依据。实际入口、阶段流转和页面衔接如下。

### 1. 前端入口与路由

- 应用入口在 `frontend/src/App.tsx`。
- 登录态通过 `/api/auth/me`、`/api/auth/login`、`/api/auth/logout` 维护。
- 登录成功后默认进入 `/plan`，其余工作流页面为 `/trace`、`/quality`、`/template`。

### 2. 预案生成主流程

`/plan` 页面是当前主工作流入口。用户输入故障问题后，前端调用 `runPipelineStream`，请求 `/api/pipeline/run`。开发环境下由 `frontend/server/proxy.mjs` 做简化代理；当前更完整的实际部署链路由 `docker/frontend-proxy/server.py` 承担鉴权、SSE 转发、案例检索协同、多故障分支控制以及后续 `/trace`、`/quality`、`/template` 等接口聚合，并统一调度 `scripts/run_parallel_generation_pipeline.py`。

当前前端识别并展示的流水线阶段为：

1. `basic_info`：获取基本信息，提取用户问题、故障场景、图谱检索素材。
2. `template_split`：切分模板，返回模板 ID、模板名、版本和章节数，并初始化章节列表。
3. `parallel_generating`：并行生成章节，逐章接收 `chapter_started`、`chapter_chunk`、`chapter_done` 事件，前端实时拼接每章输出。
4. `case_search`：可选案例检索阶段，返回知识库、检索问题、命中文档卡片和摘要。
5. `done`：流水线完成，前端合并章节结果并进入可复用状态。

前端提交参数当前包括：

- `question`：用户输入的问题。
- `enableCaseSearch`：是否开启案例检索。
- `enableMultiFaultSearch`：是否开启多故障检索。

### 3. 结果沉淀与后续页面

`/plan` 生成完成后，前端会把 `question + pipeline` 快照写入浏览器本地存储 `llmkg_saved_plan_snapshot_v1`。后续页面都基于这个快照继续工作，而不是要求用户重复输入。

- `/trace`：调用 `/api/trace/subgraph`，利用上一步得到的 `question`、`faultScene`、`graphMaterial` 查询 Nebula 子图，展示设备根节点、主故障二级节点、命中节点与关系边。
- `/quality`：读取已生成章节，调用 `/api/quality/review` 对每章执行格式优化、原文评估和优化后评估，并支持流式返回推理与输出。
- `/template`：调用 `/api/template/sections`、`/api/template/section/save`、`/api/template/section/reset` 查看和维护模板配置。

### 4. 代理与后端衔接

前端本地代理位于 `frontend/server/proxy.mjs`，主要用于本地开发时转发主流水线请求；当前部署环境中的完整代理位于 `docker/frontend-proxy/server.py`。两者当前确认的职责包括：

1. 接收 `/api/pipeline/run` 和 `/api/plan/generate` 请求。
2. 以子进程方式执行 `scripts/run_parallel_generation_pipeline.py`。
3. 在非流式模式下直接返回 `pipeline_result.json`。
4. 在流式模式下将脚本输出转换为 SSE 事件，推送给前端页面。
5. 在部署代理中额外提供 `/api/auth/*`、`/api/trace/subgraph`、`/api/quality/review`、`/api/template/*` 等接口。
6. 根据 `enableCaseSearch` 与 `enableMultiFaultSearch` 参数协同触发案例检索与多故障查询分支。

### 5. 与历史 FastGPT JSON 的关系

- `fastGPT_json/` 仍保留多份历史工作流导出文件，用于实验记录和节点设计参考。
- 当前 README 中描述的“工作流流程”以前端实际运行链路为准，即 `App.tsx -> planApi.ts -> /api/pipeline/run -> run_parallel_generation_pipeline.py -> trace/quality/template`。

## 核心技术链路

1. 原始设备资料整理为分层故障文本，存放于 `txt/`。
2. 通过 `scripts/` 中的脚本生成图谱 Excel、知识库分块文件和辅助导入资产。
3. 将图谱数据导入 Nebula，使用 `nebula-docker-compose/` 中的 DDL、DML、索引和校验脚本完成建库。
4. 通过 `scripts/nebula_http_gateway.py` 提供 HTTP 查询入口。
5. 在 FastGPT 中使用内容提取、HTTP、代码、循环、变量更新、回答生成等节点拼接完整问答流程。

## 前端原型现状

前端代码位于 `frontend/`，是一个基于 `React 19 + Vite + Ant Design + G6` 的论文演示版原型。当前实现已经不止“结果展示页”，而是覆盖了从登录到生成、再到溯源和质检的完整前端操作链路。

### 当前已实现页面

- `/login`：账号登录页，前端会调用 `/api/auth/me`、`/api/auth/login`、`/api/auth/logout` 做基础身份校验。
- `/plan`：预案生成主页面，支持输入故障场景、随机填充示例问题、开启案例搜索、开启多故障检索、流式展示章节生成结果、复制全部结果、下载 Markdown，以及在本地缓存最近一次生成结果。
- `/trace`：图谱溯源页，会基于最近一次生成结果中的设备与故障信息请求 `/api/trace/subgraph`，并用 G6 展示命中故障节点、上下游关系和子图统计信息。
- `/quality`：格式优化与质量评估页，支持按章节流式执行“格式优化 / 原文评估 / 优化后评估”，也支持批量并发处理；顶部提示词可加载、缓存、编辑和保存。
- `/template`：模板查看页，展示章节模板配置；管理员可修改 `source_type`、`fixed_text`、`gen_instruction`，也可恢复默认值。

### 当前前端串接的后端能力

- `frontend/server/proxy.mjs` 已接通 `/api/pipeline/run`，适合作为本地开发时的最小代理。
- `docker/frontend-proxy/server.py` 已接通登录鉴权、主流水线、案例检索、图谱溯源、质量评估和模板管理，是当前更完整的部署侧接口实现。
- 前端已为案例检索预留完整展示区域，可显示知识库名称、查询问题、命中文档卡片、相关性和摘要内容。
- 前端已支持从最近一次预案结果继续进入图谱溯源和质量评估，不需要用户重复录入问题。

### 当前边界与说明

- 目前仓库内已经包含较完整的部署代理实现 `docker/frontend-proxy/server.py`，但其运行仍依赖当前服务器环境中的 FastGPT、Nebula HTTP Gateway、密钥文件和模板图空间等外部运行条件。
- 前端已有管理员/普通用户权限分层，但更完整的历史记录管理、在线协作编辑、移动端适配和复杂执行路径调试视图仍未固化为成熟产品能力。
- `docs/frontend/README.md` 中“当前前端只交付两大功能”的表述已经落后于代码，现阶段应以 `frontend/src/` 的实际实现和本 README 为准。

## 主要仓库结构

- `docs/`：阶段总结、技术记录、中期检查对照和方案说明。
- `txt/`：各设备故障层级梳理文本，是图谱与知识库构建的基础语料。
- `xls/`：图谱源 Excel、样式版、中间产物和最终成品。
- `scripts/`：图谱构建、知识库分块、Excel 兼容处理、校验和 HTTP 网关脚本。
- `知识库导入数据/`：目前最成熟的 FastGPT 导入资产，已重点覆盖断路器和输电线。
- `nebula-docker-compose/`：Nebula 的部署、初始化、导入、索引和验证脚本。
- `fastGPT_json/`：FastGPT 工作流导出文件，是当前原型能力的直接体现。

## 代表性产物

- 断路器知识库导入包：
  `知识库导入数据/断路器/csv/kb_chunks_fastgpt_upload_retrieval_only_corrected_v6_missing_marked.txt`
- 输电线知识库导入包：
  `知识库导入数据/输电线/20_upload_chunks/kb_chunks_transmission_retrieval_only_v4_missing_marked.txt`
- 断路器图谱成品：
  `xls/成品/高压断路器/`
- 输电线路图谱成品：
  `xls/成品/输电线路/`
- 光缆、环网柜、变压器、互感器图谱成品：
  `xls/成品/光缆/`、`xls/成品/环网柜/`、`xls/成品/变压器/`、`xls/成品/互感器/`

## 当前主要问题

- FastGPT 末端生成节点仍有间歇性空响应，稳定性还需要继续联调。
- 二级故障匹配在口语化输入场景下仍存在误判风险。
- 多设备统一工作流已经起步，但尚未完全固化为最终版本。
- 量化评测、批量回归和论文实验结果整理仍在推进。

## 仓库现状总结

这个仓库目前已经不是“前期资料收集”阶段，而是一个已经具备可运行原型的中期项目：数据资产已经成形，图数据库链路已经打通，FastGPT 节点流程已经从单轮检索演进到带缓存和循环的查询编排，下一步重点是多设备统一化、稳定性提升和实验评测固化。
