import { useCallback, useMemo, useState } from 'react';
import { message } from 'antd';
import { runPipelineStream } from '../../services/planApi';
import { downloadText } from '../../utils/download';
import type { PipelineChapter, PipelineRunResponse, PipelineStage } from '../../types/plan';
import { loadSavedSnapshot, saveSnapshot } from './planSnapshot';

function parseFaultScene(text: string) {
  try {
    return JSON.parse(text || '{}') as Record<string, unknown>;
  } catch {
    return {};
  }
}

export type UsePlanPipelineOptions = {
  onUnauthorized?: () => void;
};

export function usePlanPipeline(options: UsePlanPipelineOptions = {}) {
  const savedSnapshot = loadSavedSnapshot();
  const [question, setQuestion] = useState(savedSnapshot?.question || '');
  const [pipeline, setPipeline] = useState<PipelineRunResponse | null>(savedSnapshot?.pipeline || null);
  const [stage, setStage] = useState<PipelineStage>(savedSnapshot?.pipeline ? 'done' : 'idle');
  const [nodeStageLabel, setNodeStageLabel] = useState(savedSnapshot?.pipeline ? '已恢复上次生成结果' : '等待输入');
  const [loading, setLoading] = useState(false);
  const [enableCaseSearch, setEnableCaseSearch] = useState(false);
  const [enableMultiFaultSearch, setEnableMultiFaultSearch] = useState(false);
  const [savedFlag, setSavedFlag] = useState(Boolean(savedSnapshot?.pipeline));
  const [questionPopoverOpen, setQuestionPopoverOpen] = useState(false);

  const chapters = pipeline?.chapters ?? [];
  const mergedOutput = useMemo(
    () => chapters.map((item) => `# ${item.chapterNo} ${item.title}\n\n${item.outputText}`).join('\n\n'),
    [chapters]
  );

  const summaryTags = useMemo(() => {
    if (!pipeline) return [];
    const parsed = parseFaultScene(pipeline.basicInfo.faultScene);
    const faultNodes = parsed['故障二级节点'];
    const faultTags = Array.isArray(faultNodes)
      ? faultNodes.map((item) => String(item)).filter(Boolean)
      : faultNodes
        ? [String(faultNodes)]
        : [];
    return [
      ...faultTags,
      parsed['故障对象'] ? String(parsed['故障对象']) : '',
      pipeline.templateSplit.templateName,
      `${pipeline.templateSplit.chapterCount}章`
    ].filter(Boolean) as string[];
  }, [pipeline]);

  const caseCards = useMemo(() => pipeline?.caseSearch?.cards || [], [pipeline?.caseSearch?.cards]);

  const handleGenerate = useCallback(async () => {
    if (!question.trim()) {
      message.warning('请先输入故障场景描述');
      return;
    }

    setLoading(true);
    setPipeline({
      question,
      basicInfo: {
        userQuestion: question,
        faultScene: '',
        graphMaterial: ''
      },
      templateSplit: {
        templateId: '',
        templateName: '',
        currentVersion: '',
        chapterCount: 0
      },
      chapters: []
    });
    setStage('basic_info');
    setNodeStageLabel('正在获取基本信息');

    try {
      await runPipelineStream(
        { question, enableCaseSearch, enableMultiFaultSearch },
        {
          onStage: (nextStage, detail) => {
            if (nextStage === 'basic_info') {
              setStage('basic_info');
              setNodeStageLabel('正在获取基本信息');
              if (detail?.faultScene || detail?.graphMaterial || detail?.userQuestion) {
                setPipeline((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    basicInfo: {
                      userQuestion: detail?.userQuestion || prev.basicInfo.userQuestion || '',
                      faultScene: detail?.faultScene || prev.basicInfo.faultScene || '',
                      graphMaterial: detail?.graphMaterial || prev.basicInfo.graphMaterial || ''
                    }
                  };
                });
              }
            }
            if (nextStage === 'template_split') {
              setStage('template_split');
              setNodeStageLabel('正在切分模板');
            }
            if (nextStage === 'parallel_generating') {
              setStage('parallel_generating');
              setNodeStageLabel('正在并行生成章节');
            }
            if (nextStage === 'case_search') {
              setNodeStageLabel('正在并行生成章节并检索案例');
            }
          },
          onTemplateSplit: (payload) => {
            setPipeline((prev) => ({
              question: prev?.question || question,
              basicInfo: prev?.basicInfo || {
                userQuestion: question,
                faultScene: '',
                graphMaterial: ''
              },
              templateSplit: payload?.templateSplit || {
                templateId: '',
                templateName: '',
                currentVersion: '',
                chapterCount: 0
              },
              chapters: (payload?.chapters || []).map((chapter: any) => ({
                chapterNo: String(chapter.chapterNo || ''),
                title: String(chapter.title || ''),
                sectionCount: Number(chapter.sectionCount || 0),
                templateText: String(chapter.templateText || ''),
                outputText: '',
                status: 'pending'
              })),
              caseSearch:
                prev?.caseSearch ||
                (enableCaseSearch
                  ? {
                      enabled: true,
                      status: 'idle'
                    }
                  : undefined)
            }));
          },
          onChapterStarted: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? { ...chapter, status: 'running' }
                    : chapter
                )
              };
            });
          },
          onChapterDone: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? {
                        ...chapter,
                        outputText: String(payload?.outputText || ''),
                        elapsedSec: typeof payload?.elapsedSec === 'number' ? payload.elapsedSec : undefined,
                        status: payload?.status === 'error' ? 'error' : 'done'
                      }
                    : chapter
                )
              };
            });
          },
          onChapterChunk: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? {
                        ...chapter,
                        outputText: `${chapter.outputText || ''}${String(payload?.chunk || '')}`,
                        status: 'running'
                      }
                    : chapter
                )
              };
            });
          },
          onCaseSearchStarted: (payload) => {
            setNodeStageLabel('正在并行生成章节并检索案例');
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: 'running',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: '',
                  cards: prev.caseSearch?.cards || []
                }
              };
            });
          },
          onCaseSearchDone: (payload) => {
            setStage('done');
            setNodeStageLabel('生成完成');
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: 'done',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: payload?.output_text ? String(payload.output_text) : '',
                  cards: Array.isArray(payload?.cards) ? payload.cards : []
                }
              };
            });
          },
          onCaseSearchError: (payload) => {
            if (payload?.status === 'skipped') {
              setStage('done');
              setNodeStageLabel('生成完成');
            } else {
              setStage('error');
              setNodeStageLabel('案例检索失败');
            }
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: payload?.status === 'skipped' ? 'skipped' : 'error',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: '',
                  cards: prev.caseSearch?.cards || [],
                  error: payload?.error ? String(payload.error) : payload?.message ? String(payload.message) : ''
                }
              };
            });
          },
          onDone: (result) => {
            setLoading(false);
            setPipeline((prev) => {
              const nextPipeline = {
                ...result,
                caseSearch: prev?.caseSearch || result.caseSearch
              };
              saveSnapshot(question, nextPipeline);
              setSavedFlag(true);
              return nextPipeline;
            });
            setStage('done');
            setNodeStageLabel('生成完成');
            message.success(`已生成 ${result.chapters.length} 个章节`);
          }
        }
      );
    } catch (error) {
      setStage('error');
      setNodeStageLabel('生成失败');
      const err = error instanceof Error ? error.message : '未知错误';
      if ((error as any).isUnauthorized) {
        options.onUnauthorized?.();
        message.error('登录已过期，请重新登录');
        return;
      }
      message.error(err);
    } finally {
      setLoading(false);
    }
  }, [enableCaseSearch, enableMultiFaultSearch, options, question]);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(mergedOutput);
    message.success('已复制全部章节结果');
  }, [mergedOutput]);

  const handleDownload = useCallback(() => {
    downloadText('并行生成预案.md', mergedOutput);
  }, [mergedOutput]);

  const pickQuestion = useCallback((text: string) => {
    setQuestion(text);
    setQuestionPopoverOpen(false);
  }, []);

  return {
    question,
    setQuestion,
    pipeline,
    stage,
    nodeStageLabel,
    loading,
    enableCaseSearch,
    setEnableCaseSearch,
    enableMultiFaultSearch,
    setEnableMultiFaultSearch,
    savedFlag,
    chapters,
    summaryTags,
    caseCards,
    questionPopoverOpen,
    setQuestionPopoverOpen,
    pickQuestion,
    handleGenerate,
    handleCopy,
    handleDownload
  };
}

export type UsePlanPipelineResult = ReturnType<typeof usePlanPipeline>;
