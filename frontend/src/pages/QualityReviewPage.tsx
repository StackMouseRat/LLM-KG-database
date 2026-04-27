import { useEffect, useMemo, useRef, useState } from 'react';
import { message } from 'antd';
import { QualityChapterReviewGrid } from '../features/quality/QualityChapterReviewGrid';
import { QualityPromptPanel } from '../features/quality/QualityPromptPanel';
import { fetchTemplatePrompts, saveTemplatePrompt } from '../features/quality/qualityApi';
import { loadPromptCache, loadReviewCache, loadSavedPipeline, savePromptCache, saveReviewCache } from '../features/quality/qualityStorage';
import type { LeftCardView, PromptConfig, ReviewStatus, StreamTarget } from '../features/quality/types';

const BATCH_REVIEW_CONCURRENCY = 6;

function isRunningStatus(status: ReviewStatus) {
  return status === 'started' || status === 'thinking' || status === 'generating';
}

export function QualityReviewPage({
  currentUserGroup,
  showModeTags,
  compactLayout
}: {
  currentUserGroup: 'admin' | 'user';
  showModeTags: boolean;
  compactLayout: boolean;
}) {
  const pipeline = useMemo(() => loadSavedPipeline(), []);
  const chapters = pipeline?.chapters || [];
  const faultScene = pipeline?.basicInfo?.faultScene || '';
  const graphMaterial = pipeline?.basicInfo?.graphMaterial || '';
  const leftBodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const rightBodyRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [prompts, setPrompts] = useState<PromptConfig[]>(() => loadPromptCache() || []);
  const [promptLoading, setPromptLoading] = useState(false);
  const [editingPromptKey, setEditingPromptKey] = useState('');
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const [savingPromptKey, setSavingPromptKey] = useState('');
  const reviewCache = useRef(loadReviewCache());
  const [optimizeReasoningMap, setOptimizeReasoningMap] = useState<Record<string, string>>(reviewCache.current?.optimizeReasoningMap || {});
  const [rawEvaluateReasoningMap, setRawEvaluateReasoningMap] = useState<Record<string, string>>(reviewCache.current?.rawEvaluateReasoningMap || {});
  const [optimizedEvaluateReasoningMap, setOptimizedEvaluateReasoningMap] = useState<Record<string, string>>(reviewCache.current?.optimizedEvaluateReasoningMap || {});
  const [optimizedMap, setOptimizedMap] = useState<Record<string, string>>(reviewCache.current?.optimizedMap || {});
  const [rawEvaluationMap, setRawEvaluationMap] = useState<Record<string, string>>(reviewCache.current?.rawEvaluationMap || {});
  const [optimizedEvaluationMap, setOptimizedEvaluationMap] = useState<Record<string, string>>(reviewCache.current?.optimizedEvaluationMap || {});
  const [optimizeStatusMap, setOptimizeStatusMap] = useState<Record<string, ReviewStatus>>(reviewCache.current?.optimizeStatusMap || {});
  const [rawEvaluateStatusMap, setRawEvaluateStatusMap] = useState<Record<string, ReviewStatus>>(reviewCache.current?.rawEvaluateStatusMap || {});
  const [optimizedEvaluateStatusMap, setOptimizedEvaluateStatusMap] = useState<Record<string, ReviewStatus>>(reviewCache.current?.optimizedEvaluateStatusMap || {});
  const [leftCardViewMap, setLeftCardViewMap] = useState<Record<string, LeftCardView>>(reviewCache.current?.leftCardViewMap || {});
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
      const items = await fetchTemplatePrompts();
      setPrompts(items);
      savePromptCache(items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提示词加载失败');
    } finally {
      setPromptLoading(false);
    }
  };

  const reviewSaveCounter = useRef(0);
  const [reviewSaveTick, setReviewSaveTick] = useState(0);

  useEffect(() => {
    void loadPrompts(false);
  }, []);

  const persistReviewCache = () => {
    reviewSaveCounter.current += 1;
    setReviewSaveTick(reviewSaveCounter.current);
  };

  useEffect(() => {
    if (!reviewSaveCounter.current) return;
    saveReviewCache({
      optimizeStatusMap,
      optimizeReasoningMap,
      optimizedMap,
      rawEvaluateStatusMap,
      rawEvaluateReasoningMap,
      rawEvaluationMap,
      optimizedEvaluateStatusMap,
      optimizedEvaluateReasoningMap,
      optimizedEvaluationMap,
      leftCardViewMap,
    });
  }, [reviewSaveTick]);

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
      const updated = await saveTemplatePrompt(promptKey, promptDrafts[promptKey] || '');
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
    if (!chapterTemplateText?.trim()) {
      return basePrompt;
    }
    if (target === 'optimize') {
      return `${basePrompt}\n\n当前章节生成模板：\n${chapterTemplateText}\n\n请严格参考该章节生成模板，对正文进行格式优化，尽量使输出结构、标题层级与内容组织更贴近模板要求，但不要改变原始业务含义和处置步骤。`;
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
        content: text,
        faultScene,
        graphMaterial
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
        persistReviewCache();
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
      <QualityPromptPanel
        chaptersLength={chapters.length}
        promptLoading={promptLoading}
        prompts={prompts}
        canManagePrompts={canManagePrompts}
        editingPromptKey={editingPromptKey}
        promptDrafts={promptDrafts}
        savingPromptKey={savingPromptKey}
        batchOptimizeLoading={batchOptimizeLoading}
        batchRawEvaluateLoading={batchRawEvaluateLoading}
        batchOptimizedEvaluateLoading={batchOptimizedEvaluateLoading}
        batchBusy={batchBusy}
        hasBatchRawEvaluableChapters={hasBatchRawEvaluableChapters}
        hasBatchOptimizedEvaluableChapters={hasBatchOptimizedEvaluableChapters}
        onRunBatchReview={(target) => void runBatchReview(target)}
        onBeginEditPrompt={beginEditPrompt}
        onCancelEditPrompt={cancelEditPrompt}
        onSavePrompt={(promptKey) => void savePrompt(promptKey)}
        onLoadPrompts={(forceRefresh) => void loadPrompts(forceRefresh)}
        onChangePromptDraft={(promptKey, value) =>
          setPromptDrafts((prev) => ({
            ...prev,
            [promptKey]: value
          }))
        }
      />

      <QualityChapterReviewGrid
        chapters={chapters}
        compactLayout={compactLayout}
        showModeTags={showModeTags}
        leftBodyRefs={leftBodyRefs}
        rightBodyRefs={rightBodyRefs}
        optimizeReasoningMap={optimizeReasoningMap}
        rawEvaluateReasoningMap={rawEvaluateReasoningMap}
        optimizedEvaluateReasoningMap={optimizedEvaluateReasoningMap}
        optimizedMap={optimizedMap}
        rawEvaluationMap={rawEvaluationMap}
        optimizedEvaluationMap={optimizedEvaluationMap}
        optimizeStatusMap={optimizeStatusMap}
        rawEvaluateStatusMap={rawEvaluateStatusMap}
        optimizedEvaluateStatusMap={optimizedEvaluateStatusMap}
        leftCardViewMap={leftCardViewMap}
        onChangeLeftCardView={(chapterNo, value) =>
          setLeftCardViewMap((prev) => ({
            ...prev,
            [chapterNo]: value
          }))
        }
        onOptimize={(chapterNo, text, chapterTemplateText) => void handleOptimize(chapterNo, text, chapterTemplateText)}
        onRawEvaluate={(chapterNo, text, chapterTemplateText) =>
          void handleRawEvaluate(chapterNo, text, chapterTemplateText)
        }
        onOptimizedEvaluate={(chapterNo, text, chapterTemplateText) =>
          void handleOptimizedEvaluate(chapterNo, text, chapterTemplateText)
        }
      />
    </div>
  );
}
