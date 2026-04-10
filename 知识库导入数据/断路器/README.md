# 断路器应急预案检索资产

## 目录结构
- csv/
  - template_sections.csv
  - plan_facts.csv
  - plan_actions.csv
  - org_clauses.csv
  - contacts.csv
  - kb_chunks.csv
- workflow/
  - fastgpt_node_blueprint.csv
  - fastgpt_node_edges.json
  - fastgpt_retrieval_profile.json
  - fastgpt_slot_schema.json

## 数据来源
- 原始图谱目录: D:\Graduate_test\dataset\xls\成品\high_voltage_breaker_1to8_import4
- 生成时间: 2026-04-10 19:43:47

## 使用方式
1. 将 `csv/kb_chunks.csv` 导入 FastGPT 知识库。
2. 按 `workflow/fastgpt_node_blueprint.csv` 在工作流中创建节点。
3. 按 `workflow/fastgpt_node_edges.json` 连线。
4. 将 `workflow/fastgpt_retrieval_profile.json` 的检索参数填入 3 个知识库搜索节点。
5. 在“参数提取”节点套用 `workflow/fastgpt_slot_schema.json` 约束输出。

## 说明
- 本方案为“语义检索”优先配置。
- 若后续切换混合检索，可在检索节点开启全文+重排，并把最低相关度提高到 0.65~0.75。
