# 实验页面变体脚本

本目录保存 `/experiment` 页面各实验组对应的修改版运行脚本。每个脚本都接收与主流水线相同的基础参数，最常用参数为：

```bash
python3 scripts/experiment_page_variants/boundary_no_boundary.py --question "今天吃什么？"
```

脚本对应关系：

- `boundary_no_boundary.py`：输入边界实验 / 实验组一 / 移除输入边界校验
- `boundary_keyword_boundary.py`：输入边界实验 / 实验组二 / 关键词边界校验
- `disambiguation_drop_subject.py`：设备主体消歧实验 / 实验组一 / 移除主体判定
- `disambiguation_keyword_subject.py`：设备主体消歧实验 / 实验组二 / 关键词主体判定
- `graph_template_no_graph.py`：图谱与模板约束实验 / 实验组一 / 移除图谱
- `graph_template_no_template.py`：图谱与模板约束实验 / 实验组二 / 移除模板
- `multi_fault_single_fault.py`：多故障链式实验 / 实验组一 / 单故障普通链路
- `multi_fault_no_per_fault_graph.py`：多故障链式实验 / 实验组二 / 识别多故障但不逐项检索

`common.py` 是通用运行器，负责复用现有 FastGPT 插件调用、模板切片、章节生成与结果落盘逻辑。
