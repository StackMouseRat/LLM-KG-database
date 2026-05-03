# BLEU/ROUGE 轻量基线与 LLM-as-Judge 对比

本说明提供一个“轻量实验”脚本，用于把现有实验运行结果中的各实验组输出，与对照组输出做 BLEU/ROUGE 对比，并与已保存的 LLM-as-Judge 分数做相关性分析。

## 1. 脚本位置

- `scripts/metrics_lite_compare.py`

## 2. 输入数据来源

脚本直接复用现有实验产物目录：

- `.../{planId}/{runId}/experiment_run.json`
- `.../{planId}/{runId}/experiment_evaluation.json`

默认根目录是容器路径：`/app/data/frontend_experiment_runs`。

本地开发机可显式传入：

- `--runs-root /home/ubuntu/LLM-KG-database/tmp/your_runs_dir`

## 3. 评估逻辑（轻量版）

- 参考文本（reference）：默认使用 `control` 组输出（可用 `--reference-group` 改）。
- 候选文本（candidate）：默认使用其余实验组输出（可用 `--target-groups` 指定）。
- 逐轮、逐组计算：`BLEU-1/2/3/4`、`ROUGE-L(F1)`。
- 从 `experiment_evaluation.json` 读取 `structuredEvaluation.score` 作为 LLM-as-Judge 分数。
- 汇总输出：
  - 总体均值（BLEU/ROUGE/LLM 分数）
  - 按组均值
  - 与 LLM 分数的 Pearson/Spearman 相关系数

## 4. 用法示例

```bash
python3 scripts/metrics_lite_compare.py \
  --plan-id disambiguation \
  --run-id disambiguation_1714999999999_ab12cd \
  --runs-root /app/data/frontend_experiment_runs \
  --out tmp/metrics/disambiguation_lite_compare.json
```

只比较指定实验组：

```bash
python3 scripts/metrics_lite_compare.py \
  --plan-id graphTemplate \
  --run-id graphTemplate_1714999999999_ab12cd \
  --target-groups exp-no-graph,exp-no-template
```

## 5. 结果解读建议

- BLEU/ROUGE 高，通常表示“文本重叠高”，但不必然等价于“事实正确”。
- LLM-as-Judge 分数更贴合任务定义（结构完整、事实相关、可执行性等），但存在模型评判偏差。
- 建议在论文中并列报告：
  - `LLM-as-Judge` 主结果
  - `BLEU/ROUGE` 作为轻量补充指标
  - 二者相关系数作为一致性证据

## 6. 当前限制

- 该轻量版使用“对照组输出”作为伪参考，不是人工金标准答案。
- 中文分词采用“字粒度 + 英文词”的简化策略，便于零依赖运行。
- 若要更严谨，可在后续版本引入：
  - 人工参考答案
  - jieba 或专业中文分词
  - bootstrap 显著性检验
