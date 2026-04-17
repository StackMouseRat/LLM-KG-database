# FastGPT 34条故障描述并发测试

## 目录说明
- `questions_34.txt`: 34条测试问题（每行一条）
- `run_fastgpt_batch_test.py`: 滚动并发测试脚本（并发上限默认10）
- `outputs/`: 运行结果输出目录（自动生成）
- `outputs/raw/`: 每条请求的原始响应（JSON）

## 运行方式
在仓库根目录执行：

```powershell
python .\batch_test_34\run_fastgpt_batch_test.py
```

默认行为：
- `chat-mode=shared`（所有问题复用同一个 `chatId`，连续对话）
- `max-concurrency=1`（顺序执行，不并发）

可选参数：

```powershell
python .\batch_test_34\run_fastgpt_batch_test.py `
  --base-url http://localhost:3000/api `
  --api-key-file .\api\testkey.txt `
  --questions-file .\batch_test_34\questions_34.txt `
  --chat-mode shared `
  --chat-id my_chat_id `
  --max-concurrency 1 `
  --limit 0 `
  --timeout 120
```

输出文件：
- 汇总：`batch_test_34/outputs/results_YYYYMMDD_HHMMSS.txt`
- 原始响应：`batch_test_34/outputs/raw/*.json`
