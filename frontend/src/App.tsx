import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Button, Card, Checkbox, Collapse, Input, Layout, message, Space, Tag, Typography } from 'antd';
import { CopyOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { PipelineChapter, PipelineRunResponse, PipelineStage } from './types/plan';
import { runPipelineStream } from './services/planApi';
import { downloadText } from './utils/download';

const { Header, Content } = Layout;
const { TextArea } = Input;

const demoQuestion =
  '暴雨导致电缆沟进水，开关柜出现绝缘告警，夜间值班，无法立即更换设备，需要一份简短的双阶段处置方案。';

const stageText: Record<PipelineStage, string> = {
  idle: '等待输入',
  basic_info: '正在获取基本信息',
  template_split: '正在切分模板',
  parallel_generating: '正在并行生成章节',
  case_search: '正在检索案例',
  done: '生成完成',
  error: '生成失败'
};

function renderInlineText(text: string): ReactNode[] {
  const parts = text.split(/(\[KG\]|\[GEN\]|\[FIX\]|\*\*[^*]+\*\*)/g);
  return parts
    .filter((part) => part !== '')
    .map((part, index) => {
      if (part === '[KG]') {
        return (
          <Tag color="blue" key={index}>
            KG
          </Tag>
        );
      }
      if (part === '[GEN]') {
        return (
          <Tag color="orange" key={index}>
            GEN
          </Tag>
        );
      }
      if (part === '[FIX]') {
        return (
          <Tag color="green" key={index}>
            FIX
          </Tag>
        );
      }
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return <span key={index}>{part}</span>;
    });
}

function renderMarkedText(text: string, options?: { normalize?: boolean }) {
  const normalizedText = options?.normalize === false ? String(text || '') : normalizeRenderedOutput(text);
  return (
    <div className="rendered-rich-text">
      {normalizedText.split('\n').map((line, index) => {
        const trimmed = line.trim();

        if (!trimmed) {
          return <div className="render-blank" key={index} />;
        }

        if (trimmed.startsWith('#### ')) {
          return (
            <div className="render-h4" key={index}>
              {renderInlineText(trimmed.slice(5))}
            </div>
          );
        }

        if (trimmed.startsWith('### ')) {
          return (
            <div className="render-h3" key={index}>
              {renderInlineText(trimmed.slice(4))}
            </div>
          );
        }

        if (trimmed.startsWith('## ')) {
          return (
            <div className="render-h2" key={index}>
              {renderInlineText(trimmed.slice(3))}
            </div>
          );
        }

        if (trimmed.startsWith('# ')) {
          return (
            <div className="render-h1" key={index}>
              {renderInlineText(trimmed.slice(2))}
            </div>
          );
        }

        return (
          <div className="render-line" key={index}>
            {renderInlineText(line)}
          </div>
        );
      })}
    </div>
  );
}

function normalizeRenderedOutput(text: string) {
  const raw = String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/([^\n])(#{1,4}\s+)/g, '$1\n$2')
    .replace(/([^\n])(第[一二三四五六七八九十0-9]+章)/g, '$1\n$2')
    .replace(/([^\n])(案例[一二三四五六七八九十百千0-9]+[：:\s])/g, '$1\n$2')
    .replace(/([^\n])(---+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\s+)/g, '$1\n$2')
    .replace(/([^\n])(内容来源：|图谱字段：|预定义文本：|生成要求：)/g, '$1\n$2');
  const headingPattern = /(^|\n)(#{1,4}\s+[^\n]+|第[一二三四五六七八九十0-9]+章[^\n]*)/m;
  const match = raw.match(headingPattern);

  if (!match || typeof match.index !== 'number') {
    return cleanupInlineMetaLines(promoteStructuredHeadings(raw));
  }

  const startIndex = match[1] ? match.index + match[1].length : match.index;
  return cleanupInlineMetaLines(promoteStructuredHeadings(raw.slice(startIndex).trimStart()));
}

function cleanupInlineMetaLines(text: string) {
  const patterns = ['内容来源：', '图谱字段：', '预定义文本：', '生成要求：'];
  return text
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) return true;
      if (/^!\[.*\]\(.*\)$/.test(trimmed)) return false;
      if (/^\[图像内容省略\]$/.test(trimmed)) return false;
      return !patterns.some((marker) => trimmed.includes(marker));
    })
    .join('\n');
}

function promoteStructuredHeadings(text: string) {
  const lines = text.split('\n');
  const normalized: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    let line = lines[i].trim();

    if (!line) {
      normalized.push('');
      continue;
    }

    if (/^#{1,6}$/.test(line)) {
      continue;
    }

    if (/^GEN/.test(line)) {
      line = line.replace(/^GEN/, '').trim();
    } else if (/^KG/.test(line)) {
      line = line.replace(/^KG/, '').trim();
    } else if (/^FIX/.test(line)) {
      line = line.replace(/^FIX/, '').trim();
    }

    if (!line) {
      continue;
    }

    if (/^第[一二三四五六七八九十百千0-9]+章\s+.+$/.test(line)) {
      normalized.push(`# ${line}`);
      continue;
    }

    if (/^案例[一二三四五六七八九十百千0-9]+[：:\s].+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^---+$/.test(line)) {
      normalized.push('');
      continue;
    }

    normalized.push(line);
  }

  return normalized.join('\n');
}

function parseFaultScene(text: string) {
  try {
    return JSON.parse(text || '{}') as Record<string, string>;
  } catch {
    return {};
  }
}

type CaseSearchCard = {
  rank: string;
  title: string;
  kbId: string;
  docId: string;
  relevance: string;
  excerpt: string;
};

function parseCaseSearchCards(text: string): CaseSearchCard[] {
  const normalized = String(text || '').replace(/\r/g, '');
  const blocks = normalized
    .split(/\n\s*---+\s*\n/g)
    .map((item) => item.trim())
    .filter(Boolean);

  return blocks
    .map((block) => {
      const lines = block.split('\n');
      let rank = '';
      let title = '';
      let kbId = '';
      let docId = '';
      let relevance = '';
      const excerptLines: string[] = [];
      let inExcerpt = false;

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('### 命中 ')) {
          rank = trimmed.slice('### 命中 '.length).trim();
          continue;
        }
        if (trimmed.startsWith('- 标题：')) {
          title = trimmed.slice('- 标题：'.length).trim();
          continue;
        }
        if (trimmed.startsWith('- 知识库ID：')) {
          kbId = trimmed.slice('- 知识库ID：'.length).trim();
          continue;
        }
        if (trimmed.startsWith('- 文档ID：')) {
          docId = trimmed.slice('- 文档ID：'.length).trim();
          continue;
        }
        if (trimmed.startsWith('- 相关性：')) {
          relevance = trimmed.slice('- 相关性：'.length).trim();
          continue;
        }
        if (trimmed === '- 摘要：') {
          inExcerpt = true;
          continue;
        }
        if (inExcerpt) {
          excerptLines.push(line);
        }
      }

      return {
        rank,
        title,
        kbId,
        docId,
        relevance,
        excerpt: excerptLines.join('\n').trim()
      };
    })
    .filter((item) => item.title || item.excerpt);
}

export default function App() {
  const [question, setQuestion] = useState(demoQuestion);
  const [pipeline, setPipeline] = useState<PipelineRunResponse | null>(null);
  const [stage, setStage] = useState<PipelineStage>('idle');
  const [nodeStageLabel, setNodeStageLabel] = useState('等待输入');
  const [loading, setLoading] = useState(false);
  const [enableCaseSearch, setEnableCaseSearch] = useState(false);

  const chapters = pipeline?.chapters ?? [];
  const mergedOutput = useMemo(
    () => chapters.map((item) => `# ${item.chapterNo} ${item.title}\n\n${item.outputText}`).join('\n\n'),
    [chapters]
  );

  const summaryTags = useMemo(() => {
    if (!pipeline) return [];
    const parsed = parseFaultScene(pipeline.basicInfo.faultScene);
    return [
      parsed['故障二级节点'],
      parsed['故障对象'],
      pipeline.templateSplit.templateName,
      `${pipeline.templateSplit.chapterCount}章`
    ].filter(Boolean) as string[];
  }, [pipeline]);
  const caseCards = useMemo(
    () => parseCaseSearchCards(pipeline?.caseSearch?.outputText || ''),
    [pipeline?.caseSearch?.outputText]
  );

  const handleGenerate = async () => {
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
        { question, enableCaseSearch },
        {
          onStage: (nextStage) => {
            if (nextStage === 'basic_info') {
              setStage('basic_info');
              setNodeStageLabel('正在获取基本信息');
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
                  outputText: ''
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
                  outputText: payload?.output_text ? String(payload.output_text) : ''
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
                  error: payload?.error ? String(payload.error) : payload?.message ? String(payload.message) : ''
                }
              };
            });
          },
          onDone: (result) => {
            setLoading(false);
            setPipeline((prev) => ({
              ...result,
              caseSearch: prev?.caseSearch || result.caseSearch
            }));
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
      message.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(mergedOutput);
    message.success('已复制全部章节结果');
  };

  const handleDownload = () => {
    downloadText('并行生成预案.md', mergedOutput);
  };

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <div>
          <Typography.Title level={3} className="app-title">
            电力设备并行预案生成系统
          </Typography.Title>
        </div>
      </Header>
      <Content className="app-content">
        <div className="pipeline-page">
          <Card title="故障场景输入" className="panel-card pipeline-input-card">
            <TextArea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
              placeholder="请输入故障问题或场景，例如：暴雨导致电缆沟进水..."
            />
            <Space className="action-row" wrap>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={handleGenerate}>
                运行流水线
              </Button>
              <Button onClick={() => setQuestion(demoQuestion)}>填入示例</Button>
              <Button size="small" icon={<CopyOutlined />} disabled={!chapters.length} onClick={handleCopy}>
                复制全部
              </Button>
              <Button size="small" icon={<DownloadOutlined />} disabled={!chapters.length} onClick={handleDownload}>
                下载全部
              </Button>
              <Checkbox checked={enableCaseSearch} onChange={(event) => setEnableCaseSearch(event.target.checked)}>
                开启案例搜索
              </Checkbox>
            </Space>
            <div className="status-box">
              <Tag color={stage === 'error' ? 'red' : stage === 'done' ? 'green' : 'processing'}>
                {stageText[stage]}
              </Tag>
              <Tag>{nodeStageLabel}</Tag>
              {summaryTags.map((tag) => (
                <Tag color="purple" key={tag}>
                  {tag}
                </Tag>
              ))}
            </div>
          </Card>

          <div
            className="chapter-row"
            style={
              chapters.length
                ? {
                    gridTemplateColumns: `repeat(${chapters.length}, minmax(0, 1fr))`
                  }
                : undefined
            }
          >
            {chapters.length ? (
              chapters.map((chapter: PipelineChapter) => (
                <Card
                  key={`${chapter.chapterNo}-${chapter.title}`}
                  className="panel-card chapter-panel"
                  title={`${chapter.chapterNo} ${chapter.title}`}
                  extra={
                    <Tag color={chapter.status === 'done' ? 'green' : chapter.status === 'error' ? 'red' : 'processing'}>
                      {chapter.status}
                    </Tag>
                  }
                >
                  <div className="chapter-meta">耗时：{chapter.elapsedSec ?? '-'}s · 小节数：{chapter.sectionCount}</div>
                  <Collapse
                    size="small"
                    className="chapter-collapse"
                    items={[
                      {
                        key: 'template',
                        label: '章节模板',
                        children: <div className="chapter-template-text">{chapter.templateText}</div>
                      }
                    ]}
                  />
                  <div className="chapter-panel__body">
                    {chapter.outputText ? (
                      renderMarkedText(chapter.outputText, { normalize: false })
                    ) : (
                      <Typography.Text type="secondary">本章节暂无输出。</Typography.Text>
                    )}
                  </div>
                </Card>
              ))
            ) : (
              <Card className="panel-card chapter-empty-card">
                <Typography.Text type="secondary">
                  运行后，每个章节会以一个独立竖向输出框显示在这里，并横向排列。
                </Typography.Text>
              </Card>
            )}
          </div>

          <Card title="案例检索" className="panel-card chapter-empty-card">
            {pipeline?.caseSearch?.enabled ? (
              pipeline.caseSearch.status === 'done' && pipeline.caseSearch.outputText ? (
                <>
                  <div className="chapter-meta">
                    知识库：{pipeline.caseSearch.kbName || '-'} · 查询：{pipeline.caseSearch.queryQuestion || '-'}
                  </div>
                  {caseCards.length ? (
                    <div className="case-card-grid">
                      {caseCards.map((card, index) => (
                        <div className="case-search-card" key={`${card.rank}-${card.title}-${index}`}>
                        <div className="case-search-card__header">
                          <Tag color="blue">命中 {card.rank || index + 1}</Tag>
                        </div>
                        <div className="case-search-card__title">{card.title || '未命名案例'}</div>
                        <div className="case-search-card__meta-inline">
                          {card.kbId ? (
                            <span className="case-search-card__pill">
                              <span className="case-search-card__pill-label">知识库ID</span>
                              <span className="case-search-card__pill-value">{card.kbId}</span>
                            </span>
                          ) : null}
                          {card.docId ? (
                            <span className="case-search-card__pill">
                              <span className="case-search-card__pill-label">文档ID</span>
                              <span className="case-search-card__pill-value">{card.docId}</span>
                            </span>
                          ) : null}
                          {card.relevance ? (
                            <span className="case-search-card__pill case-search-card__pill--score">
                              <span className="case-search-card__pill-label">相关性</span>
                              <span className="case-search-card__pill-value">{card.relevance}</span>
                            </span>
                          ) : null}
                        </div>
                          <div className="case-search-card__excerpt">
                            {card.excerpt ? renderMarkedText(card.excerpt) : <Typography.Text type="secondary">无摘要</Typography.Text>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    renderMarkedText(pipeline.caseSearch.outputText)
                  )}
                </>
              ) : pipeline.caseSearch.status === 'running' ? (
                <Typography.Text type="secondary">正在检索案例，请稍候。</Typography.Text>
              ) : pipeline.caseSearch.status === 'skipped' ? (
                <Typography.Text type="secondary">
                  未命中已建立知识库对应设备，已跳过案例检索。
                </Typography.Text>
              ) : pipeline.caseSearch.status === 'error' ? (
                <Typography.Text type="danger">
                  案例检索失败：{pipeline.caseSearch.error || '未知错误'}
                </Typography.Text>
              ) : (
                <Typography.Text type="secondary">等待开始案例检索。</Typography.Text>
              )
            ) : (
              <Typography.Text type="secondary">未开启案例搜索。</Typography.Text>
            )}
          </Card>
        </div>
      </Content>
    </Layout>
  );
}
