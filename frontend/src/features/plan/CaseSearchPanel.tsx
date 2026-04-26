import { Card, Tag, Typography } from 'antd';
import { RichTextRenderer } from '../../components/RichTextRenderer';
import type { UsePlanPipelineResult } from './usePlanPipeline';

type CaseSearchPanelProps = {
  plan: UsePlanPipelineResult;
  showModeTags: boolean;
};

export function CaseSearchPanel({ plan, showModeTags }: CaseSearchPanelProps) {
  return (
    <Card title="案例检索" className="panel-card chapter-empty-card">
      {plan.pipeline?.caseSearch?.enabled ? (
        plan.pipeline.caseSearch.status === 'done' && plan.caseCards.length > 0 ? (
          <>
            <div className="chapter-meta">
              知识库：{plan.pipeline.caseSearch.displayName || plan.pipeline.caseSearch.kbName || '-'} · 查询：
              {plan.pipeline.caseSearch.queryQuestion || '-'}
            </div>
            <div className="case-card-grid">
              {plan.caseCards.map((card, index) => (
                <div className="case-search-card" key={`${card.id || index}-${card.title}`}>
                  <div className="case-search-card__header">
                    <Tag color="blue">命中 {index + 1}</Tag>
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
                    {card.excerpt ? (
                      <RichTextRenderer text={card.excerpt} showModeTags={showModeTags} />
                    ) : (
                      <Typography.Text type="secondary">无摘要</Typography.Text>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : plan.pipeline.caseSearch.status === 'running' ? (
          <Typography.Text type="secondary">正在检索案例，请稍候。</Typography.Text>
        ) : plan.pipeline.caseSearch.status === 'skipped' ? (
          <Typography.Text type="secondary">
            未命中已建立知识库对应设备，已跳过案例检索。
          </Typography.Text>
        ) : plan.pipeline.caseSearch.status === 'error' ? (
          <Typography.Text type="danger">
            案例检索失败：{plan.pipeline.caseSearch.error || '未知错误'}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">
            {plan.stage !== 'idle' ? '等待识别设备…' : '等待开始案例检索。'}
          </Typography.Text>
        )
      ) : (
        <Typography.Text type="secondary">未开启案例搜索。</Typography.Text>
      )}
    </Card>
  );
}
