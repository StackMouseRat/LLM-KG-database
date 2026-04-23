import { useMemo, useState } from 'react';
import { Button, Card, Empty, Space, Tag, Typography, message } from 'antd';
import { RichTextRenderer } from '../components/RichTextRenderer';
import type { PipelineRunResponse } from '../types/plan';

const PLAN_SNAPSHOT_KEY = 'llmkg_saved_plan_snapshot_v1';

const optimizePrompt = `请对预案正文进行格式优化：
1. 保留原始章节编号和标题层级
2. 修复换行、标题粘连、列表错位
3. 删除无意义的元信息噪声
4. 不改变业务含义和处置步骤
5. 输出适合正式预案阅读的规范文本`;

const evaluatePrompt = `请对预案正文进行质量评估：
1. 检查结构是否完整
2. 检查章节编号是否连续
3. 检查是否存在重复、缺项、逻辑跳跃
4. 检查应急动作是否可执行
5. 输出简短的质量结论与修改建议`;

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

function normalizePlanText(text: string) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function evaluatePlanText(text: string) {
  const normalized = normalizePlanText(text);
  const headingCount = (normalized.match(/^#{1,4}\s+/gm) || []).length;
  const paragraphCount = normalized ? normalized.split(/\n\s*\n/).filter(Boolean).length : 0;
  const hasReport = normalized.includes('信息报告');
  const hasMeasures = normalized.includes('处置措施');
  const hasRecovery = normalized.includes('恢复');
  const notes = [
    `章节标题数：${headingCount}`,
    `段落数：${paragraphCount}`,
    `是否包含“信息报告”：${hasReport ? '是' : '否'}`,
    `是否包含“处置措施”：${hasMeasures ? '是' : '否'}`,
    `是否包含“恢复”相关内容：${hasRecovery ? '是' : '否'}`
  ];
  const summary = hasReport && hasMeasures ? '结构基本完整，可继续人工复核细节。' : '结构可能不完整，建议补充关键章节。';
  return `【质量评估】\n${notes.join('\n')}\n\n结论：${summary}`;
}

export function QualityReviewPage() {
  const pipeline = useMemo(() => loadSavedPipeline(), []);
  const chapters = pipeline?.chapters || [];
  const [optimizedMap, setOptimizedMap] = useState<Record<string, string>>({});
  const [evaluationMap, setEvaluationMap] = useState<Record<string, string>>({});

  const handleOptimize = (chapterNo: string, text: string) => {
    setOptimizedMap((prev) => ({
      ...prev,
      [chapterNo]: normalizePlanText(text)
    }));
    message.success(`已生成第 ${chapterNo} 章的优化结果`);
  };

  const handleEvaluate = (chapterNo: string, text: string) => {
    setEvaluationMap((prev) => ({
      ...prev,
      [chapterNo]: evaluatePlanText(text)
    }));
    message.success(`已完成第 ${chapterNo} 章的质量评估`);
  };

  return (
    <div className="pipeline-page">
      <div className="quality-summary-grid">
        <Card title="格式优化与质量评估" className="panel-card">
          <Typography.Paragraph className="app-subtitle">
            当前页面为占位页，后续将接入预案正文格式规范化、结构检查、缺项提示和质量评估结果。
          </Typography.Paragraph>
          <div className="status-box">
            <Tag color="gold">占位页</Tag>
            <Tag>待接入格式优化与质量评估工作流</Tag>
          </div>
        </Card>
        <Card title="优化提示词" className="panel-card">
          <div className="template-field__value template-field__value--long">{optimizePrompt}</div>
        </Card>
        <Card title="评估提示词" className="panel-card">
          <div className="template-field__value template-field__value--long">{evaluatePrompt}</div>
        </Card>
      </div>

      {chapters.length ? (
        <div className="quality-compare-grid">
          {chapters.map((chapter) => {
            const optimizedText = optimizedMap[chapter.chapterNo] || '';
            const evaluationText = evaluationMap[chapter.chapterNo] || '';
            return (
              <>
                <Card
                  key={`raw-${chapter.chapterNo}`}
                  className="panel-card quality-plan-card"
                  title={`${chapter.chapterNo} ${chapter.title} · 原文`}
                  extra={<Tag color="blue">原文</Tag>}
                >
                  <div className="chapter-meta">小节数：{chapter.sectionCount} · 耗时：{chapter.elapsedSec ?? '-'}s</div>
                  <div className="quality-actions">
                    <Space wrap>
                      <Button size="small" onClick={() => handleOptimize(chapter.chapterNo, chapter.outputText)}>
                        优化
                      </Button>
                      <Button size="small" onClick={() => handleEvaluate(chapter.chapterNo, chapter.outputText)}>
                        评估
                      </Button>
                    </Space>
                  </div>
                  <div className="quality-plan-card__body">
                    <RichTextRenderer text={chapter.outputText} normalize={false} stripMeta emptyText="暂无原文内容。" />
                  </div>
                </Card>

                <Card
                  key={`opt-${chapter.chapterNo}`}
                  className="panel-card quality-plan-card"
                  title={`${chapter.chapterNo} ${chapter.title} · 优化后`}
                  extra={<Tag color="green">优化后</Tag>}
                >
                  <div className="chapter-meta">展示优化结果与质量评估</div>
                  <div className="quality-plan-card__body">
                    <RichTextRenderer
                      text={
                        optimizedText
                          ? `${optimizedText}${evaluationText ? `\n\n${evaluationText}` : ''}`
                          : ''
                      }
                      normalize={false}
                      stripMeta
                      emptyText="点击左侧“优化”按钮后在此显示优化后的预案文本。"
                    />
                  </div>
                </Card>
              </>
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
