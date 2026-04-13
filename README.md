# LLM-KG Database

## 当前目录结构
- `docs/`：说明文档与方案记录（含 `Plan_model.txt`）
- `img/`：图片资源
- `txt/`：图谱梳理文本
- `xls/`：图谱源 Excel 与成品数据
- `scripts/`：数据构建与转换脚本
- `知识库导入数据/`：可直接导入 FastGPT 的结构化数据与上传包
- `nebula-docker-compose/`：Nebula 图数据库导入、索引、校验脚本
- `fastGPT_json/`：FastGPT 工作流导出 JSON

## 知识库导入资产（2026-04-11）

### 断路器
- 上传文件：`知识库导入数据/断路器/csv/kb_chunks_fastgpt_upload_retrieval_only_corrected_v6_missing_marked.txt`
- 结构化文件：`知识库导入数据/断路器/csv/kb_chunks_corrected_v6_missing_marked.csv`

### 输电线
- 上传文件：`知识库导入数据/输电线/20_upload_chunks/kb_chunks_transmission_retrieval_only_v4_missing_marked.txt`
- 结构化文件：`知识库导入数据/输电线/10_csv_structured/kb_chunks_transmission_v4_missing_marked.csv`

## 缺失槽位标记
对模板要求但图谱缺失的槽位，自动追加：`[[MISSING_FROM_GRAPH]]`。
该标记用于生成阶段提示模型进行谨慎补全。

## 关键脚本
- `scripts/build_breaker_kb_chunks_name_desc.py`：断路器 name+desc 增强构建
- `scripts/build_add_missing_slot_markers.py`：断路器/输电线缺失槽位标记后处理

## FastGPT 推荐参数
- 分块方式：指定分隔符 `<<<CHUNK>>>`
- 搜索方式：语义检索
- 问题优化：开启
- 最低相关度：`0.72`（可在 `0.70~0.75` 调整）
- 引用上限：`1800` tokens

## Nebula + HTTP 网关（2026-04-14）
- 网关脚本：`scripts/nebula_http_gateway.py`
- Compose 文件：`nebula-docker-compose/docker-compose-lite.yaml`
- 主要导入脚本：
  - `nebula-docker-compose/import_breaker_full_step1_ddl.ngql`
  - `nebula-docker-compose/import_breaker_full_step2_dml.ngql`
  - `nebula-docker-compose/import_breaker_full_step3_index.ngql`
- 主要校验脚本：
  - `nebula-docker-compose/check_schema_ready.ngql`
  - `nebula-docker-compose/verify_breaker_full_import.ngql`
  - `nebula-docker-compose/verify_desc_import.ngql`

## FastGPT 工作流（当前版本）
- 工作流 JSON：`fastGPT_json/测试 Copy.json`
- 核心链路：
  1. 首次运行先查询并缓存“一二级故障目录”。
  2. 计划器基于用户问题 + 目录缓存生成分步查询计划。
  3. 循环节点逐步执行：查询体生成 -> HTTP 请求 Nebula -> 查询后处理 -> 结果累积。
  4. 循环结束输出整合后的自然语言答复。

## 今日变更记录
- 总结文档：`docs/2026-04-14-work-summary.md`
