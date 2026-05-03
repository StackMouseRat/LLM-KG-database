# 传统自动指标与 LLM-as-Judge 对比审计

本文档记录基于首批 180 组实验样本的传统自动指标与 LLM-as-Judge 对比审计结果，用于说明在电气设备应急预案生成任务中，仅依赖 BLEU、ROUGE-L、chrF++、BERTScore 等指标存在局限，LLM-as-Judge 更适合作为主评价方法。

## 1. 数据与脚本

- 输入结果：`tmp/metrics/first_batch_metrics_rouge_chrf_bertscore.json`
- 审计脚本：`scripts/audit_metric_vs_llm_judge.py`
- 输出结果：`tmp/metrics/metric_vs_llm_judge_audit.json`

运行命令：

```bash
python3 scripts/audit_metric_vs_llm_judge.py \
  --input tmp/metrics/first_batch_metrics_rouge_chrf_bertscore.json \
  --out tmp/metrics/metric_vs_llm_judge_audit.json
```

## 2. 总体相关性

| 指标 | Pearson | Spearman | 高指标低 LLM 数量 | 低指标高 LLM 数量 |
| --- | ---: | ---: | ---: | ---: |
| ROUGE-L | 0.4923 | 0.4179 | 4 | 4 |
| chrF++ | 0.5044 | 0.3472 | 8 | 4 |
| BERTScore F1 | 0.5695 | 0.4214 | 6 | 4 |

结果显示，BERTScore F1 与 LLM-as-Judge 的 Pearson 相关性最高，但也仅为 0.5695，Spearman 相关性为 0.4214。传统指标与 LLM 评分存在中等相关，但不能完全替代面向任务质量的综合判断。

## 3. 分场景相关性

多故障场景中，传统指标与 LLM 评分出现明显背离：

| 实验运行 | 现象 |
| --- | --- |
| `multiFault/multiFault_1777729066432_42b8ee` | BERTScore F1 与 LLM 评分负相关，Pearson 为 -0.1558 |
| `multiFault/multiFault_1777801282989_f20dce` | BERTScore F1 与 LLM 评分负相关，Pearson 为 -0.4170 |

这说明在多故障并发、逐故障图谱覆盖、恢复验证等复杂任务中，候选预案即使与对照组存在较高语义相似度，也可能遗漏关键故障链、误判主体或缺少验证闭环，从而被 LLM-as-Judge 给出较低分。

## 4. 典型失效案例

### 4.1 高 BERTScore 但 LLM 低分

示例：`multiFault/multiFault_1777729066432_42b8ee` 第 3 轮。

- 问题：某电流互感器二次开路导致保护采样异常和电流表指示接近零，请生成应急方案。
- 实验组：`exp-single-fault`
- BERTScore F1：0.8495
- LLM-as-Judge：5.0

该样本在词汇和语义表达上与对照组高度接近，因此 BERTScore 得分较高。但 LLM-as-Judge 能进一步检查预案是否覆盖关键处置链路、风险控制、验证与恢复条件，因此给出较低分。

### 4.2 chrF++ 排序与 LLM 排序反转

示例：`graphTemplate/graphTemplate_1777793822792_1c4b91` 第 14 轮。

- 问题：某电流互感器二次开路处理完成后，请生成包含响应终止和测量恢复验证的方案。
- chrF++ 更高的组：`exp-no-graph`，chrF++ 为 0.4992，LLM 分数为 5.7。
- LLM 评分更高的组：`exp-no-template`，chrF++ 为 0.3131，LLM 分数为 7.4。

该案例说明，字符级相似度更高的文本不一定更符合任务目标。LLM-as-Judge 能识别“响应终止条件”“测量恢复验证”“安全措施复归”等任务要求是否被实质性满足。

## 5. 论文表述建议

可写入论文的结论如下：

> 为验证传统自动评价指标在本任务中的适用性，本文进一步计算 ROUGE-L、chrF++ 与 BERTScore F1，并将其与 LLM-as-Judge 评分进行相关性分析。在 180 组实验样本上，BERTScore F1 与 LLM-as-Judge 的 Pearson 相关性最高，为 0.5695，但 Spearman 相关性仅为 0.4214；ROUGE-L 和 chrF++ 也仅表现出中等相关性。进一步的分场景分析表明，在多故障并发场景中，BERTScore F1 与 LLM-as-Judge 评分甚至出现负相关，说明传统指标难以充分识别故障主体、处置链完整性、图谱覆盖、模板约束和恢复验证等专业质量维度。因此，本文将传统自动指标作为辅助 baseline，而采用 LLM-as-Judge 作为主要自动评价方法。

## 6. 方法优越性总结

LLM-as-Judge 的优势主要体现在：

- 能判断故障主体是否正确，而不是只统计文本相似度。
- 能检查预案章节、处置步骤、恢复验证和安全风险是否完整。
- 能识别多故障场景中的遗漏故障、主次关系错误和图谱覆盖不足。
- 能结合任务要求进行综合评分，避免高相似度文本被误判为高质量预案。
