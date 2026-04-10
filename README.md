# LLM-KG Database

## 当前目录结构
- `docs/`：说明文档与方案记录（含 `Plan_model.txt`）
- `img/`：图片资源
- `txt/`：图谱梳理文本
- `xls/`：图谱源 Excel 与成品数据
- `scripts/`：数据构建与转换脚本
- `知识库导入数据/`：可直接导入 FastGPT 的结构化数据与上传包

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
