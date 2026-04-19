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

### 正在推进

- 正在把单设备验证流程扩展为多设备统一入口工作流。
- 正在补齐光缆、环网柜等新设备的图谱自动生成脚本与成品资产。
- 正在进行案例验证、生成稳定性优化和量化评测设计。

### 当前阶段判断

- 第一阶段：资料整理与模板结构设计，已完成。
- 第二阶段：知识图谱本体与结构化资产构建，已完成。
- 第三阶段：FastGPT 工作流与图查询链路，已完成可运行版本。
- 第四阶段：原型联调、案例验证、评测与论文实验，进行中。

## FastGPT 工作流现状

`fastGPT_json/` 目录下当前共有 4 个工作流 JSON。下面按文件逐一列出节点排布和连线关系。

### `fastGPT_json/测试.json`

节点从左到右排布如下：

1. `common:core.module.template.system_config`，类型 `userGuide`
2. `common:core.module.template.work_start`，类型 `workflowStart`
3. `问题优化`，类型 `cfr`
4. `文本内容提取`，类型 `contentExtract`
5. `知识库搜索`，类型 `datasetSearchNode`
6. `提取数据清洗`，类型 `contentExtract`
7. `最终生成`，类型 `chatNode`

主连线顺序如下：

1. `workflowStart -> 问题优化`
2. `问题优化 -> 文本内容提取`
3. `文本内容提取 -> 知识库搜索`
4. `知识库搜索 -> 提取数据清洗`
5. `提取数据清洗 -> 最终生成`

### `fastGPT_json/断路器测试工作流.json`

顶层节点从左到右排布如下：

1. `common:core.module.template.system_config`，类型 `userGuide`
2. `common:core.module.template.work_start`，类型 `workflowStart`
3. `缓存初始化数据`，类型 `ifElseNode`
4. `基础数据获取`，类型 `httpRequest468`
5. `基础数据清洗`，类型 `code`
6. `基础数据更新`，类型 `variableUpdate`
7. `故障类型分析`，类型 `contentExtract`
8. `下游节点获取`，类型 `httpRequest468`
9. `下游节点数据清洗`，类型 `code`
10. `最终生成`，类型 `chatNode`
11. `指定回复`，类型 `answerNode`

主连线顺序如下：

1. `workflowStart -> 缓存初始化数据`
2. `缓存初始化数据 -> 基础数据获取`
3. `基础数据获取 -> 基础数据清洗`
4. `基础数据清洗 -> 基础数据更新`
5. `基础数据更新 -> 故障类型分析`
6. `缓存初始化数据 -> 故障类型分析`
7. `故障类型分析 -> 下游节点获取`
8. `下游节点获取 -> 下游节点数据清洗`
9. `下游节点数据清洗 -> 最终生成`
10. `最终生成 -> 指定回复`

### `fastGPT_json/测试 Copy.json`

顶层节点从左到右排布如下：

1. `common:core.module.template.system_config`，类型 `userGuide`
2. `common:core.module.template.work_start`，类型 `workflowStart`
3. `缓存初始化数据`，类型 `ifElseNode`
4. `基础数据获取`，类型 `httpRequest468`
5. `基础数据清洗`，类型 `code`
6. `基础数据更新`，类型 `variableUpdate`
7. `计划器`，类型 `contentExtract`
8. `批量执行`，类型 `loop`

`批量执行` 循环子图内部节点从左到右排布如下：

1. `开始`，类型 `loopStart`
2. `循环提取`，类型 `contentExtract`
3. `HTTP 请求`，类型 `httpRequest468`
4. `查询后处理`，类型 `chatNode`
5. `变量更新`，类型 `variableUpdate`
6. `结束`，类型 `loopEnd`

顶层与循环子图的主连线顺序如下：

1. `workflowStart -> 缓存初始化数据`
2. `缓存初始化数据 -> 基础数据获取`
3. `基础数据获取 -> 基础数据清洗`
4. `基础数据清洗 -> 基础数据更新`
5. `基础数据更新 -> 计划器`
6. `缓存初始化数据 -> 计划器`
7. `计划器 -> 批量执行`
8. `开始 -> 循环提取`
9. `循环提取 -> HTTP 请求`
10. `HTTP 请求 -> 查询后处理`
11. `查询后处理 -> 变量更新`
12. `变量更新 -> 结束`

### `fastGPT_json/多设备测试工作流.json`

顶层节点从左到右排布如下：

1. `common:core.module.template.system_config`，类型 `userGuide`
2. `common:core.module.template.work_start`，类型 `workflowStart`
3. `设备表初始化`，类型 `ifElseNode`
4. `获取全体设备表`，类型 `httpRequest468`
5. `清洗设备表数据`，类型 `code`
6. `设备识别`，类型 `contentExtract`
7. `基础数据获取`，类型 `httpRequest468`
8. `基础数据清洗`，类型 `code`
9. `故障类型分析`，类型 `contentExtract`
10. `下游节点获取`，类型 `httpRequest468`
11. `下游节点数据清洗`，类型 `code`
12. `最终生成`，类型 `chatNode`
13. `指定回复`，类型 `answerNode`

主连线顺序如下：

1. `workflowStart -> 设备表初始化`
2. `设备表初始化 -> 获取全体设备表`
3. `获取全体设备表 -> 清洗设备表数据`
4. `清洗设备表数据 -> 设备识别`
5. `设备表初始化 -> 设备识别`
6. `设备识别 -> 基础数据获取`
7. `基础数据获取 -> 基础数据清洗`
8. `基础数据清洗 -> 故障类型分析`
9. `故障类型分析 -> 下游节点获取`
10. `下游节点获取 -> 下游节点数据清洗`
11. `下游节点数据清洗 -> 最终生成`
12. `最终生成 -> 指定回复`

## 核心技术链路

1. 原始设备资料整理为分层故障文本，存放于 `txt/`。
2. 通过 `scripts/` 中的脚本生成图谱 Excel、知识库分块文件和辅助导入资产。
3. 将图谱数据导入 Nebula，使用 `nebula-docker-compose/` 中的 DDL、DML、索引和校验脚本完成建库。
4. 通过 `scripts/nebula_http_gateway.py` 提供 HTTP 查询入口。
5. 在 FastGPT 中使用内容提取、HTTP、代码、循环、变量更新、回答生成等节点拼接完整问答流程。

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
