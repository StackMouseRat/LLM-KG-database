import { Card, Collapse, Tag, Typography } from 'antd';
import { RichTextRenderer } from '../../components/RichTextRenderer';
import type { PipelineChapter } from '../../types/plan';

const chapterStatusText: Record<'pending' | 'running' | 'done' | 'error', string> = {
  pending: '等待中',
  running: '生成中',
  done: '已完成',
  error: '失败'
};

type PlanChapterGridProps = {
  chapters: PipelineChapter[];
  showModeTags: boolean;
  showCompactLayout: boolean;
};

export function PlanChapterGrid({ chapters, showModeTags, showCompactLayout }: PlanChapterGridProps) {
  return (
    <div
      className="chapter-row"
      style={
        chapters.length
          ? {
              gridTemplateColumns: showCompactLayout
                ? 'repeat(3, minmax(0, 1fr))'
                : `repeat(${chapters.length}, minmax(0, 1fr))`
            }
          : undefined
      }
    >
      {chapters.length ? (
        chapters.map((chapter) => (
          <Card
            key={`${chapter.chapterNo}-${chapter.title}`}
            className="panel-card chapter-panel"
            title={`${chapter.chapterNo} ${chapter.title}`}
            extra={
              <Tag color={chapter.status === 'done' ? 'green' : chapter.status === 'error' ? 'red' : 'processing'}>
                {chapterStatusText[chapter.status]}
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
                <RichTextRenderer text={chapter.outputText} normalize={false} stripMeta showModeTags={showModeTags} />
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
  );
}
