import type { MutableRefObject } from 'react';
import { Fragment } from 'react';
import { Button, Card, Empty, Segmented, Space, Tag } from 'antd';
import { RichTextRenderer } from '../../components/RichTextRenderer';
import type { PipelineChapter } from '../../types/plan';
import type { LeftCardView, ReviewStatus } from './types';

function isRunningStatus(status: ReviewStatus) {
  return status === 'started' || status === 'thinking' || status === 'generating';
}

type QualityChapterReviewGridProps = {
  chapters: PipelineChapter[];
  compactLayout: boolean;
  showModeTags: boolean;
  leftBodyRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  rightBodyRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  optimizeReasoningMap: Record<string, string>;
  rawEvaluateReasoningMap: Record<string, string>;
  optimizedEvaluateReasoningMap: Record<string, string>;
  optimizedMap: Record<string, string>;
  rawEvaluationMap: Record<string, string>;
  optimizedEvaluationMap: Record<string, string>;
  optimizeStatusMap: Record<string, ReviewStatus>;
  rawEvaluateStatusMap: Record<string, ReviewStatus>;
  optimizedEvaluateStatusMap: Record<string, ReviewStatus>;
  leftCardViewMap: Record<string, LeftCardView>;
  onChangeLeftCardView: (chapterNo: string, value: LeftCardView) => void;
  onOptimize: (chapterNo: string, text: string, chapterTemplateText?: string) => void;
  onRawEvaluate: (chapterNo: string, text: string, chapterTemplateText?: string) => void;
  onOptimizedEvaluate: (chapterNo: string, text: string, chapterTemplateText?: string) => void;
};

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

export function QualityChapterReviewGrid({
  chapters,
  compactLayout,
  showModeTags,
  leftBodyRefs,
  rightBodyRefs,
  optimizeReasoningMap,
  rawEvaluateReasoningMap,
  optimizedEvaluateReasoningMap,
  optimizedMap,
  rawEvaluationMap,
  optimizedEvaluationMap,
  optimizeStatusMap,
  rawEvaluateStatusMap,
  optimizedEvaluateStatusMap,
  leftCardViewMap,
  onChangeLeftCardView,
  onOptimize,
  onRawEvaluate,
  onOptimizedEvaluate
}: QualityChapterReviewGridProps) {
  if (!chapters.length) {
    return (
      <Card className="panel-card chapter-empty-card">
        <Empty description="未发现本地持久化的预案结果，请先在预案生成页完成一次成功生成。" />
      </Card>
    );
  }

  return (
    <div
      className="quality-compare-grid"
      style={
        compactLayout
          ? {
              gridTemplateColumns: 'repeat(4, minmax(0, 1fr))'
            }
          : undefined
      }
    >
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
                    onChange={(value) => onChangeLeftCardView(chapter.chapterNo, value as LeftCardView)}
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
                      onClick={() => onOptimize(chapter.chapterNo, chapter.outputText, chapter.templateText)}
                    >
                      优化
                    </Button>
                    <Button
                      size="small"
                      loading={rawEvaluateRunning}
                      disabled={cardBusy}
                      onClick={() => onRawEvaluate(chapter.chapterNo, chapter.outputText, chapter.templateText)}
                    >
                      评估原文
                    </Button>
                    <Button
                      size="small"
                      loading={optimizedEvaluateRunning}
                      disabled={cardBusy || !canOptimizedEvaluate}
                      onClick={() => onOptimizedEvaluate(chapter.chapterNo, optimizedText, chapter.templateText)}
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
                    showModeTags={showModeTags}
                  />
                </div>
              </Card>
            </div>

            <Card
              className="panel-card quality-plan-card"
              title={`${chapter.chapterNo} ${chapter.title} · 优化后`}
              extra={
                <Space direction="vertical" size={6}>
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
                  showModeTags={showModeTags}
                />
              </div>
            </Card>
          </Fragment>
        );
      })}
    </div>
  );
}
