# 对比评估前端接入开发顺序

## 目标

为实验页新增“对比评估”能力，满足以下要求：

1. 点击后从第一个未完成对比评估的轮次开始继续执行。
2. 对比评估并发数按轮次计算，默认值为 3，表示同时最多评估 3 个轮次。
3. 每个轮次卡片展示当前排名、相对分数和主要结论。
4. 在当前展示均分的位置，同时展示各组排第 1、2、3 名的次数与百分比。
5. 页面展示当前有哪些任务正在运行，至少区分生成、绝对评估、对比评估三类任务。
6. 对比评估支持断点续传，中途停止或刷新页面后可从第一个未完成轮次继续。

## 数据设计

### 新增文件

对比评估独立存储，不并入现有 `experiment_evaluation.json`。新增文件：

`docs/project_changes/frontend_experiment_runs/<planId>/<runId>/experiment_pairwise_evaluation.json`

### 文件结构

建议结构如下：

```json
{
  "planId": "disambiguation",
  "runId": "disambiguation_1777744159540_0268bf",
  "createdAt": "2026-05-06T10:00:00+00:00",
  "updatedAt": "2026-05-06T10:10:00+00:00",
  "pairwiseEvaluationState": {
    "status": "running",
    "progress": 57,
    "concurrency": 3,
    "activeTasks": [
      {
        "round": 22,
        "status": "running",
        "startedAt": "2026-05-06T10:20:00+00:00"
      }
    ],
    "results": {
      "22": {
        "status": "done",
        "question": "...",
        "overallRanking": [
          "control",
          "exp-drop-subject-judgement",
          "exp-keyword-subject-judgement"
        ],
        "relativeScores": {
          "control": 9,
          "exp-drop-subject-judgement": 6,
          "exp-keyword-subject-judgement": 3
        },
        "mainFindings": [
          "..."
        ],
        "summary": "...",
        "elapsedSec": 25.054,
        "evaluatedAt": "2026-05-06T10:22:00+00:00"
      }
    },
    "errors": {
      "23": {
        "message": "...",
        "updatedAt": "2026-05-06T10:24:00+00:00"
      }
    },
    "summaryStats": {
      "control": {
        "rank1": 5,
        "rank2": 1,
        "rank3": 0,
        "rank1Pct": 71.4,
        "rank2Pct": 14.3,
        "rank3Pct": 0.0
      }
    }
  }
}
```

## 接口设计

### 查询接口

`GET /api/experiment/pairwise-evaluation?planId=...&runId=...`

返回完整对比评估记录。

### 启动接口

`POST /api/experiment/pairwise-evaluation/run`

请求体：

```json
{
  "planId": "disambiguation",
  "runId": "disambiguation_1777744159540_0268bf",
  "resume": true,
  "concurrency": 3
}
```

语义：

1. `resume=true` 时跳过已完成轮次，从第一个未完成轮次继续。
2. `concurrency` 按轮次计算，表示同时最多评估多少轮。

## 后端实现顺序

### 第一步：状态文件与读写接口

文件：

1. `docker/frontend-proxy/services/experiment_service.py`
2. `docker/frontend-proxy/server.py`

实现内容：

1. 新增 `pairwise_evaluation_path(plan_id, run_id)`
2. 新增 `default_pairwise_evaluation_state()`
3. 新增 `load_pairwise_evaluation_record(plan_id, run_id)`
4. 新增 `save_pairwise_evaluation_record(plan_id, run_id, pairwise_state)`
5. 新增查询接口和保存接口骨架

本步骤先解决数据结构、路径和基础 API，不接入实际评估执行。

### 第二步：对比评估服务化

文件：

1. 新增 `docker/frontend-proxy/services/pairwise_evaluation_service.py`
2. 复用 `scripts/run_deepseek_pairwise_experiment_evaluation.py` 中的核心逻辑

实现内容：

1. 抽取按轮读取候选结果逻辑
2. 抽取构造对比评估 prompt 逻辑
3. 抽取 DeepSeek JSON 请求逻辑
4. 支持逐轮完成立即写回，而不是全部结束后一次写回

### 第三步：断点续传与调度

实现内容：

1. 找到第一个未完成轮次
2. 按 `concurrency` 同时调度多个轮次
3. 每轮完成后立即更新：
   - `results`
   - `progress`
   - `summaryStats`
   - `activeTasks`
4. 支持中途中断后继续

### 第四步：前端控制区接入

文件：

1. `frontend/src/features/experiment/experimentApi.ts`
2. `frontend/src/pages/ExperimentPage.tsx`

实现内容：

1. 新增对比评估接口调用
2. 新增“对比评估并发数”输入框，默认值 3
3. 新增“开始对比评估 / 继续对比评估”按钮
4. 展示对比评估总进度

### 第五步：运行中任务展示

文件：

1. `frontend/src/pages/ExperimentPage.tsx`
2. `frontend/src/features/experiment/ExperimentPanels.tsx`

实现内容：

1. 展示当前生成任务
2. 展示当前绝对评估任务
3. 展示当前对比评估任务
4. `activeTasks` 至少显示轮次和开始时间

### 第六步：轮次卡片展示

实现内容：

在每个轮次卡片新增“对比评估”区块，展示：

1. 排名顺序
2. 各组相对分数
3. 主要发现
4. 总体结论

### 第七步：总览统计

在当前均分区域新增“排名分布”统计：

1. 各组第 1 名次数与百分比
2. 各组第 2 名次数与百分比
3. 各组第 3 名次数与百分比

## 断点续传策略

### 原则

1. 只要轮次结果已写入 `results[round]` 且状态为 `done`，后续继续运行时就跳过。
2. 每轮完成后立即落盘，避免全部结果丢失。
3. 失败轮次写入 `errors`，再次继续时优先重试失败轮次。

### 恢复规则

恢复时轮次优先级：

1. 先重试 `errors` 中的轮次
2. 再执行未出现在 `results` 中的轮次
3. 已完成轮次跳过

## 前端展示重点

### 控制区

1. 对比评估并发数输入框
2. 对比评估开始/继续按钮
3. 对比评估进度

### 结果区

1. 每轮卡片展示对比排名与相对分数
2. 总览区展示各组排第 1/2/3 名次数与百分比
3. 单独展示当前运行中的对比评估任务

## 当前推荐开发顺序

1. 先完成后端 `experiment_pairwise_evaluation.json` 的路径、读写和接口骨架
2. 再实现对比评估服务和逐轮落盘
3. 再接入前端按钮与进度条
4. 再补运行中任务展示
5. 最后补轮次卡片与总览统计

## 本次先做的第一步

先实现：

1. `experiment_pairwise_evaluation.json` 状态文件读写
2. 后端查询/保存接口骨架

不在第一步中实现：

1. DeepSeek 对比评估实际执行
2. 前端按钮与展示
3. 统计聚合
