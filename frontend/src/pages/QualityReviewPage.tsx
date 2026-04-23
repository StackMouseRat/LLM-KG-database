import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Empty, Input, Segmented, Space, Tag, Typography, message } from 'antd';
import { RichTextRenderer } from '../components/RichTextRenderer';
import type { PipelineRunResponse } from '../types/plan';

const PLAN_SNAPSHOT_KEY = 'llmkg_saved_plan_snapshot_v1';
const PROMPT_CACHE_KEY = 'llmkg_template_prompts_cache_v1';
const BATCH_REVIEW_CONCURRENCY = 6;
const { TextArea } = Input;

type PromptConfig = {
  prompt_id: string;
  prompt_key: string;
  title: string;
  prompt_text: string;
  order_no: number;
  default?: {
    id?: string;
    prompt_key?: string;
    title?: string;
    prompt_text?: string;
    order_no?: number;
  };
};

type ReviewStatus = 'idle' | 'started' | 'thinking' | 'generating' | 'done' | 'error';
type LeftCardView = 'raw' | 'rawEvaluation' | 'optimizedEvaluation';
type StreamTarget = 'optimize' | 'rawEvaluate' | 'optimizedEvaluate';

function loadSavedPipeline(): PipelineRunResponse | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PLAN_SNAPSHOT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.pipeline && typeof parsed.pipeline === 'object' ? (parsed.pipeline as PipelineRunResponse) : null;
  } catch {
    return null;
  }
}

function loadPromptCache(): PromptConfig[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PROMPT_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PromptConfig[]) : null;
  } catch {
    return null;
  }
}

function savePromptCache(prompts: PromptConfig[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(PROMPT_CACHE_KEY, JSON.stringify(prompts));
}

function isRunningStatus(status: ReviewStatus) {
  return status === 'started' || status === 'thinking' || status === 'generating';
}

export function QualityReviewPage({ currentUserGroup }: { currentUserGroup: 'admin' | 'user' }) {
  const pipeline = useMemo(() => loadSavedPipeline(), []);
  const chapters = pipeline?.chapters || [];
  const leftBodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const rightBodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [prompts, setPrompts] = useState<PromptConfig[]>(() => loadPromptCache() || []);
  const [promptLoading, setPromptLoading] = useState(false);
  const [editingPromptKey, setEditingPromptKey] = useState('');
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const [savingPromptKey, setSavingPromptKey] = useState('');
  const [optimizeReasoningMap, setOptimizeReasoningMap] = useState<Record<string, string>>({});
  const [rawEvaluateReasoningMap, setRawEvaluateReasoningMap] = useState<Record<string, string>>({});
  const [optimizedEvaluateReasoningMap, setOptimizedEvaluateReasoningMap] = useState<Record<string, string>>({});
  const [optimizedMap, setOptimizedMap] = useState<Record<string, string>>({});
  const [rawEvaluationMap, setRawEvaluationMap] = useState<Record<string, string>>({});
  const [optimizedEvaluationMap, setOptimizedEvaluationMap] = useState<Record<string, string>>({});
  const [optimizeStatusMap, setOptimizeStatusMap] = useState<Record<string, ReviewStatus>>({});
  const [rawEvaluateStatusMap, setRawEvaluateStatusMap] = useState<Record<string, ReviewStatus>>({});
  const [optimizedEvaluateStatusMap, setOptimizedEvaluateStatusMap] = useState<Record<string, ReviewStatus>>({});
  const [leftCardViewMap, setLeftCardViewMap] = useState<Record<string, LeftCardView>>({});
  const [batchOptimizeLoading, setBatchOptimizeLoading] = useState(false);
  const [batchRawEvaluateLoading, setBatchRawEvaluateLoading] = useState(false);
  const [batchOptimizedEvaluateLoading, setBatchOptimizedEvaluateLoading] = useState(false);
  const canManagePrompts = currentUserGroup === 'admin';

  const loadPrompts = async (forceRefresh = false) => {
    if (!forceRefresh) {
      const cached = loadPromptCache();
      if (cached?.length) {
        setPrompts(cached);
        return;
      }
    }
    setPromptLoading(true);
    try {
      const response = await fetch('/api/template/prompts');
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || `请求失败：${response.status}`);
      }
      const items = Array.isArray(data?.prompts) ? (data.prompts as PromptConfig[]) : [];
      setPrompts(items);
      savePromptCache(items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提示词加载失败');
    } finally {
      setPromptLoading(false);
    }
  };

  useEffect(() => {
    void loadPrompts(false);
  }, []);

  const beginEditPrompt = (prompt: PromptConfig) => {
    setEditingPromptKey(prompt.prompt_key);
    setPromptDrafts((prev) => ({
      ...prev,
      [prompt.prompt_key]: prompt.prompt_text || ''
    }));
  };

  const cancelEditPrompt = () => {
    setEditingPromptKey('');
  };

  const savePrompt = async (promptKey: string) => {
    setSavingPromptKey(promptKey);
    try {
      const response = await fetch('/api/template/prompt/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          prompt_key: promptKey,
          prompt_text: promptDrafts[promptKey] || ''
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || `请求失败：${response.status}`);
      }
      const updated = data?.prompt as PromptConfig;
      setPrompts((prev) => {
        const next = prev.map((item) => (item.prompt_key === promptKey ? updated : item));
        savePromptCache(next);
        return next;
      });
      setEditingPromptKey('');
      message.success(`已保存：${updated?.title || promptKey}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提示词保存失败');
    } finally {
      setSavingPromptKey('');
    }
  };

  const scrollStreamingView = (chapterNo: string, target: StreamTarget) => {
    if (typeof window === 'undefined') return;
    window.requestAnimationFrame(() => {
      const container = target === 'optimize' ? rightBodyRefs.current[chapterNo] : leftBodyRefs.current[chapterNo];
      if (!container) return;
      container.scrollTop = container.scrollHeight;
    });
  };

  const buildReviewPrompt = (target: StreamTarget, chapterTemplateText?: string) => {
    const promptKey = target === 'optimize' ? 'optimize_prompt' : 'evaluate_prompt';
    const basePrompt = prompts.find((item) => item.prompt_key === promptKey)?.prompt_text || '';
    if (target === 'optimize' || !chapterTemplateText?.trim()) {
      return basePrompt;
    }
    const targetLabel = target === 'rawEvaluate' ? '原文' : '优化后的文本';
    return `${basePrompt}\n\n当前待评估对象：${targetLabel}\n\n当前章节生成模板：\n${chapterTemplateText}\n\n请结合该章节生成模板进行评估，检查正文是否符合模板预期的结构边界、内容重点与表达要求。`;
  };

  const runReviewStream = async (target: StreamTarget, chapterNo: string, text: string, chapterTemplateText?: string) => {
    const prompt = buildReviewPrompt(target, chapterTemplateText);
    if (!prompt) {
      message.error(`${target === 'optimize' ? '优化' : '评估'}提示词为空`);
      return;
    }

    if (target === 'optimize') {
      setOptimizeStatusMap((prev) => ({ ...prev, [chapterNo]: 'started' }));
      setOptimizeReasoningMap((prev) => ({ ...prev, [chapterNo]: '' }));
      setOptimizedMap((prev) => ({ ...prev, [chapterNo]: '' }));
    } else if (target === 'rawEvaluate') {
      setRawEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: 'started' }));
      setRawEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: '' }));
      setRawEvaluationMap((prev) => ({ ...prev, [chapterNo]: '' }));
    } else {
      setOptimizedEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: 'started' }));
      setOptimizedEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: '' }));
      setOptimizedEvaluationMap((prev) => ({ ...prev, [chapterNo]: '' }));
    }

    const response = await fetch('/api/quality/review', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream'
      },
      body: JSON.stringify({
        stream: true,
        mode: target === 'optimize' ? 'optimize' : 'evaluate',
        prompt,
        content: text
      })
    });

    if (!response.ok || !response.body) {
      const errText = await response.text();
      throw new Error(errText || `请求失败：${response.status}`);
    }

    const setStatus = (status: ReviewStatus) => {
      if (target === 'optimize') {
        setOptimizeStatusMap((prev) => ({ ...prev, [chapterNo]: status }));
      } else if (target === 'rawEvaluate') {
        setRawEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: status }));
      } else {
        setOptimizedEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: status }));
      }
    };

    const setReasoning = (nextValue: string) => {
      if (target === 'optimize') {
        setOptimizeReasoningMap((prev) => ({ ...prev, [chapterNo]: nextValue }));
      } else if (target === 'rawEvaluate') {
        setRawEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: nextValue }));
      } else {
        setOptimizedEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: nextValue }));
      }
    };

    const appendReasoning = (chunk: string) => {
      if (target === 'optimize') {
        setOptimizeReasoningMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      } else if (target === 'rawEvaluate') {
        setRawEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      } else {
        setOptimizedEvaluateReasoningMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      }
    };

    const appendText = (chunk: string) => {
      if (target === 'optimize') {
        setOptimizedMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      } else if (target === 'rawEvaluate') {
        setRawEvaluationMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      } else {
        setOptimizedEvaluationMap((prev) => ({ ...prev, [chapterNo]: `${prev[chapterNo] || ''}${chunk}` }));
      }
    };

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    const flushEvent = (rawChunk: string) => {
      const lines = rawChunk
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);

      let eventName = '';
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trim());
        }
      }

      let payloadData: any = {};
      const payloadText = dataLines.join('\n');
      if (payloadText) {
        try {
          payloadData = JSON.parse(payloadText);
        } catch {
          payloadData = payloadText;
        }
      }

      if (eventName === 'quality_status') {
        const status = String(payloadData?.status || '');
        if (status === 'started') setStatus('started');
        if (status === 'thinking') setStatus('thinking');
        if (status === 'generating') setStatus('generating');
        return;
      }
      if (eventName === 'quality_reasoning_chunk') {
        appendReasoning(String(payloadData?.chunk || ''));
        setStatus('thinking');
        scrollStreamingView(chapterNo, target);
        return;
      }
      if (eventName === 'quality_output_chunk') {
        setReasoning('');
        appendText(String(payloadData?.chunk || ''));
        setStatus('generating');
        scrollStreamingView(chapterNo, target);
        return;
      }
      if (eventName === 'quality_done') {
        const outputText = String(payloadData?.output_text || '');
        setReasoning('');
        if (target === 'optimize') {
          setOptimizedMap((prev) => ({ ...prev, [chapterNo]: outputText || prev[chapterNo] || '' }));
        } else if (target === 'rawEvaluate') {
          setRawEvaluationMap((prev) => ({ ...prev, [chapterNo]: outputText || prev[chapterNo] || '' }));
        } else {
          setOptimizedEvaluationMap((prev) => ({ ...prev, [chapterNo]: outputText || prev[chapterNo] || '' }));
        }
        setStatus('done');
        scrollStreamingView(chapterNo, target);
        return;
      }
      if (eventName === 'quality_error') {
        setStatus('error');
        throw new Error(payloadData?.message || '插件执行失败');
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        if (part.trim()) flushEvent(part);
      }
    }

    if (buffer.trim()) {
      flushEvent(buffer);
    }
  };

  const executeReview = async (
    target: StreamTarget,
    chapterNo: string,
    text: string,
    chapterTemplateText?: string,
    options?: { silent?: boolean }
  ) => {
    if (target === 'rawEvaluate') {
      setLeftCardViewMap((prev) => ({ ...prev, [chapterNo]: 'rawEvaluation' }));
    }
    if (target === 'optimizedEvaluate') {
      setLeftCardViewMap((prev) => ({ ...prev, [chapterNo]: 'optimizedEvaluation' }));
    }
    try {
      await runReviewStream(target, chapterNo, text, chapterTemplateText);
      if (!options?.silent) {
        const successText =
          target === 'optimize'
            ? `已生成第 ${chapterNo} 章的优化结果`
            : target === 'rawEvaluate'
              ? `已完成第 ${chapterNo} 章的原文评估`
              : `已完成第 ${chapterNo} 章的优化后评估`;
        message.success(successText);
      }
      return true;
    } catch (error) {
      if (target === 'optimize') {
        setOptimizeStatusMap((prev) => ({ ...prev, [chapterNo]: 'error' }));
      } else if (target === 'rawEvaluate') {
        setRawEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: 'error' }));
      } else {
        setOptimizedEvaluateStatusMap((prev) => ({ ...prev, [chapterNo]: 'error' }));
      }
      if (!options?.silent) {
        const errorText =
          target === 'optimize'
            ? '优化失败'
            : target === 'rawEvaluate'
              ? '原文评估失败'
              : '优化后评估失败';
        message.error(error instanceof Error ? error.message : errorText);
      }
      return false;
    }
  };

  const handleOptimize = async (chapterNo: string, text: string, chapterTemplateText?: string) => {
    await executeReview('optimize', chapterNo, text, chapterTemplateText);
  };

  const handleRawEvaluate = async (chapterNo: string, text: string, chapterTemplateText?: string) => {
    await executeReview('rawEvaluate', chapterNo, text, chapterTemplateText);
  };

  const handleOptimizedEvaluate = async (chapterNo: string, text: string, chapterTemplateText?: string) => {
    await executeReview('optimizedEvaluate', chapterNo, text, chapterTemplateText);
  };

  const runBatchReview = async (target: 'optimize' | 'rawEvaluate' | 'optimizedEvaluate') => {
    const statusMap =
      target === 'optimize'
        ? optimizeStatusMap
        : target === 'rawEvaluate'
          ? rawEvaluateStatusMap
          : optimizedEvaluateStatusMap;
    const tasks = chapters.filter((chapter) => {
      if (isRunningStatus(statusMap[chapter.chapterNo] || 'idle')) {
        return false;
      }
      if (target === 'optimize') {
        return Boolean(chapter.outputText);
      }
      if (target === 'rawEvaluate') {
        return Boolean(chapter.outputText);
      }
      return Boolean((optimizedMap[chapter.chapterNo] || '').trim());
    });

    if (!tasks.length) {
      const emptyText =
        target === 'optimize'
          ? '当前没有可批量优化的章节。'
          : target === 'rawEvaluate'
            ? '当前没有可批量评估原文的章节。'
            : '当前没有可批量评估优化后文本的章节。';
      message.info(emptyText);
      return;
    }

    if (target === 'optimize') {
      setBatchOptimizeLoading(true);
    } else if (target === 'rawEvaluate') {
      setBatchRawEvaluateLoading(true);
    } else {
      setBatchOptimizedEvaluateLoading(true);
    }

    let cursor = 0;
    let successCount = 0;
    let failCount = 0;

    try {
      const workerCount = Math.min(BATCH_REVIEW_CONCURRENCY, tasks.length);
      await Promise.all(
        Array.from({ length: workerCount }, async () => {
          while (cursor < tasks.length) {
            const currentIndex = cursor;
            cursor += 1;
            const chapter = tasks[currentIndex];
            if (!chapter) return;
            const reviewText =
              target === 'optimize'
                ? chapter.outputText
                : target === 'rawEvaluate'
                  ? chapter.outputText
                  : optimizedMap[chapter.chapterNo] || '';
            const ok = await executeReview(target, chapter.chapterNo, reviewText, chapter.templateText, { silent: true });
            if (ok) {
              successCount += 1;
            } else {
              failCount += 1;
            }
          }
        })
      );

      const summary = `${
        target === 'optimize' ? '全部优化' : target === 'rawEvaluate' ? '全部评估原文' : '全部评估优化后'
      }完成：成功 ${successCount}，失败 ${failCount}`;
      if (failCount > 0) {
        message.warning(summary);
      } else {
        message.success(summary);
      }
    } finally {
      if (target === 'optimize') {
        setBatchOptimizeLoading(false);
      } else if (target === 'rawEvaluate') {
        setBatchRawEvaluateLoading(false);
      } else {
        setBatchOptimizedEvaluateLoading(false);
      }
    }
  };

  const batchBusy = batchOptimizeLoading || batchRawEvaluateLoading || batchOptimizedEvaluateLoading;
  const hasBatchRawEvaluableChapters = chapters.some((chapter) => Boolean(chapter.outputText.trim()));
  const hasBatchOptimizedEvaluableChapters = chapters.some((chapter) => Boolean((optimizedMap[chapter.chapterNo] || '').trim()));

  return (
    <div className="pipeline-page">
      <div className="quality-summary-grid">
        <Card title="格式优化与质量评估" className="panel-card">
          <Typography.Paragraph className="app-subtitle">
            当前页面支持对已生成预案按章节执行格式优化与质量评估，结果会流式展示；思考过程先展示 reasoning，随后自动切换为模型正式输出。顶部提示词支持缓存、编辑、保存和刷新。
          </Typography.Paragraph>
          <div className="quality-actions">
            <Space wrap>
              <Button
                type="primary"
                loading={batchOptimizeLoading}
                disabled={!chapters.length || batchBusy}
                onClick={() => void runBatchReview('optimize')}
              >
                全部优化
              </Button>
              <Button
                loading={batchRawEvaluateLoading}
                disabled={!hasBatchRawEvaluableChapters || batchBusy}
                onClick={() => void runBatchReview('rawEvaluate')}
              >
                全部评估原文
              </Button>
              <Button
                loading={batchOptimizedEvaluateLoading}
                disabled={!hasBatchOptimizedEvaluableChapters || batchBusy}
                onClick={() => void runBatchReview('optimizedEvaluate')}
              >
                全部评估优化后
              </Button>
            </Space>
          </div>
          <div className="status-box">
            <Tag color="blue">按章流式处理</Tag>
            <Tag>批量并发数 {BATCH_REVIEW_CONCURRENCY}</Tag>
            <Tag>{chapters.length} 个章节</Tag>
            <Tag>{promptLoading ? '正在加载提示词' : `${prompts.length} 条提示词`}</Tag>
          </div>
        </Card>
        {['optimize_prompt', 'evaluate_prompt'].map((promptKey) => {
          const prompt = prompts.find((item) => item.prompt_key === promptKey);
          const editing = canManagePrompts && editingPromptKey === promptKey;
          return (
            <Card key={promptKey} title={prompt?.title || promptKey} className="panel-card">
              <div className="quality-actions">
                <Space wrap>
                  {canManagePrompts ? (
                    !editing ? (
                      <Button size="small" onClick={() => prompt && beginEditPrompt(prompt)}>
                        编辑
                      </Button>
                    ) : (
                      <>
                        <Button
                          size="small"
                          type="primary"
                          loading={savingPromptKey === promptKey}
                          onClick={() => savePrompt(promptKey)}
                        >
                          保存
                        </Button>
                        <Button size="small" onClick={cancelEditPrompt}>
                          取消
                        </Button>
                      </>
                    )
                  ) : null}
                  <Button size="small" loading={promptLoading} onClick={() => loadPrompts(true)}>
                    刷新
                  </Button>
                </Space>
              </div>
              {editing ? (
                <TextArea
                  className="quality-prompt-editor"
                  value={promptDrafts[promptKey] || ''}
                  autoSize={false}
                  onChange={(event) =>
                    setPromptDrafts((prev) => ({
                      ...prev,
                      [promptKey]: event.target.value
                    }))
                  }
                />
              ) : (
                <div className="template-field__value template-field__value--long quality-prompt-preview">
                  {prompt?.prompt_text || '暂无提示词内容。'}
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {chapters.length ? (
        <div className="quality-compare-grid">
          {chapters.map((chapter) => {
            const leftCardView = leftCardViewMap[chapter.chapterNo] || 'raw';
            const optimizeReasoningText = optimizeReasoningMap[chapter.chapterNo] || '';
            const rawEvaluateReasoningText = rawEvaluateReasoningMap[chapter.chapterNo] || '';
            const optimizedEvaluateReasoningText = optimizedEvaluateReasoningMap[chapter.chapterNo] || '';
            const optimizedText = optimizedMap[chapter.chapterNo] || '';
            const rawEvaluationText = rawEvaluationMap[chapter.chapterNo] || '';
            const optimizedEvaluationText = optimizedEvaluationMap[chapter.chapterNo] || '';
            const optimizeStatus = optimizeStatusMap[chapter.chapterNo] || 'idle';
            const rawEvaluateStatus = rawEvaluateStatusMap[chapter.chapterNo] || 'idle';
            const optimizedEvaluateStatus = optimizedEvaluateStatusMap[chapter.chapterNo] || 'idle';
            const optimizeRunning = isRunningStatus(optimizeStatus);
            const rawEvaluateRunning = isRunningStatus(rawEvaluateStatus);
            const optimizedEvaluateRunning = isRunningStatus(optimizedEvaluateStatus);
            const cardBusy = optimizeRunning || rawEvaluateRunning || optimizedEvaluateRunning;
            const canOptimizedEvaluate = Boolean(optimizedText.trim()) && !optimizeRunning;
            const optimizeDisplayText = optimizedText || optimizeReasoningText;
            const rawEvaluationDisplayText = rawEvaluationText || rawEvaluateReasoningText;
            const optimizedEvaluationDisplayText = optimizedEvaluationText || optimizedEvaluateReasoningText;
            const leftBodyText =
              leftCardView === 'raw'
                ? chapter.outputText
                : leftCardView === 'rawEvaluation'
                  ? rawEvaluationDisplayText
                  : optimizedEvaluationDisplayText;
            const leftEmptyText =
              leftCardView === 'raw'
                ? '暂无原文内容。'
                : leftCardView === 'rawEvaluation'
                  ? '点击“评估原文”按钮后在此显示原文评估过程与结果。'
                  : '点击“评估优化后”按钮后在此显示优化后评估过程与结果。';
            const leftMetaText =
              leftCardView === 'raw'
                ? `小节数：${chapter.sectionCount} · 耗时：${chapter.elapsedSec ?? '-'}s`
                : leftCardView === 'rawEvaluation'
                  ? '展示原文评估 reasoning 与最终评估结果'
                  : '展示优化后评估 reasoning 与最终评估结果';
            const optimizeLabelMap: Record<ReviewStatus, string> = {
              idle: '待优化',
              started: '已开始',
              thinking: '思考中',
              generating: '优化中',
              done: '优化完成',
              error: '优化失败'
            };
            const rawEvaluateLabelMap: Record<ReviewStatus, string> = {
              idle: '待评估原文',
              started: '已开始',
              thinking: '思考中',
              generating: '评估中',
              done: '原文评估完成',
              error: '原文评估失败'
            };
            const optimizedEvaluateLabelMap: Record<ReviewStatus, string> = {
              idle: '待评估优化后',
              started: '已开始',
              thinking: '思考中',
              generating: '评估中',
              done: '优化评估完成',
              error: '优化评估失败'
            };
            const optimizeColorMap: Record<ReviewStatus, string> = {
              idle: 'default',
              started: 'processing',
              thinking: 'purple',
              generating: 'cyan',
              done: 'green',
              error: 'red'
            };
            const evaluateColorMap: Record<ReviewStatus, string> = {
              idle: 'default',
              started: 'processing',
              thinking: 'purple',
              generating: 'cyan',
              done: 'green',
              error: 'red'
            };
            return (
              <Fragment key={`quality-${chapter.chapterNo}`}>
                <div className="quality-card-shell">
                  <Card
                    className="panel-card quality-plan-card"
                    title={`${chapter.chapterNo} ${chapter.title}`}
                    extra={
                      <Segmented
                        size="small"
                        value={leftCardView}
                        options={[
                          { label: '原文', value: 'raw' },
                          { label: '原文评估', value: 'rawEvaluation' },
                          { label: '优化评估', value: 'optimizedEvaluation' }
                        ]}
                        onChange={(value) =>
                          setLeftCardViewMap((prev) => ({
                            ...prev,
                            [chapter.chapterNo]: value as LeftCardView
                          }))
                        }
                      />
                    }
                  >
                    <div className="chapter-meta">{leftMetaText}</div>
                    <div className="quality-actions">
                      <Space wrap>
                        <Button
                          size="small"
                          loading={optimizeRunning}
                          disabled={cardBusy}
                          onClick={() => handleOptimize(chapter.chapterNo, chapter.outputText, chapter.templateText)}
                        >
                          优化
                        </Button>
                        <Button
                          size="small"
                          loading={rawEvaluateRunning}
                          disabled={cardBusy}
                          onClick={() => handleRawEvaluate(chapter.chapterNo, chapter.outputText, chapter.templateText)}
                        >
                          评估原文
                        </Button>
                        <Button
                          size="small"
                          loading={optimizedEvaluateRunning}
                          disabled={cardBusy || !canOptimizedEvaluate}
                          onClick={() =>
                            handleOptimizedEvaluate(chapter.chapterNo, optimizedText, chapter.templateText)
                          }
                        >
                          评估优化后
                        </Button>
                      </Space>
                    </div>
                    <div
                      className="quality-plan-card__body"
                      ref={(node) => {
                        leftBodyRefs.current[chapter.chapterNo] = node;
                      }}
                    >
                      <RichTextRenderer
                        text={leftBodyText}
                        normalize={false}
                        stripMeta
                        emptyText={leftEmptyText}
                      />
                    </div>
                  </Card>
                </div>

                <Card
                  className="panel-card quality-plan-card"
                  title={`${chapter.chapterNo} ${chapter.title} · 优化后`}
                  extra={
                    <Space size={8} wrap>
                      <Tag color={optimizeColorMap[optimizeStatus]}>{optimizeLabelMap[optimizeStatus]}</Tag>
                      <Tag color={evaluateColorMap[rawEvaluateStatus]}>{rawEvaluateLabelMap[rawEvaluateStatus]}</Tag>
                      <Tag color={evaluateColorMap[optimizedEvaluateStatus]}>
                        {optimizedEvaluateLabelMap[optimizedEvaluateStatus]}
                      </Tag>
                    </Space>
                  }
                >
                  <div className="chapter-meta">展示优化 reasoning 与优化后正文</div>
                  <div
                    className="quality-plan-card__body"
                    ref={(node) => {
                      rightBodyRefs.current[chapter.chapterNo] = node;
                    }}
                  >
                    <RichTextRenderer
                      text={optimizeDisplayText}
                      normalize={false}
                      stripMeta
                      emptyText="点击左侧“优化”按钮后在此流式显示优化过程与输出结果。"
                    />
                  </div>
                </Card>
              </Fragment>
            );
          })}
        </div>
      ) : (
        <Card className="panel-card chapter-empty-card">
          <Empty description="未发现本地持久化的预案结果，请先在预案生成页完成一次成功生成。" />
        </Card>
      )}
    </div>
  );
}
