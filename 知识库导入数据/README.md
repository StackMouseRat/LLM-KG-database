# 知识库导入数据

## 目录
- 断路器：已整理的知识库导入数据与工作流配置
- 输电线：已创建构建骨架，待生成 CSV 与上传分块

## 输电线下一步
1. 从 40_notes/source_candidates.txt 选择最终源目录
2. 生成 structured CSV（template_sections/plan_facts/plan_actions/org_clauses/contacts/kb_chunks）
3. 生成 FastGPT 上传文件（retrieval_only）
4. 跑召回测试并微调阈值
