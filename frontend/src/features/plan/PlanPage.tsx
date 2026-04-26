import { Button, Card, Checkbox, Collapse, Input, Popover, Space, Tag, Typography } from 'antd';
import { CopyOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { RichTextRenderer } from '../../components/RichTextRenderer';
import { DEVICE_QUESTIONS } from '../../data/presetQuestions';
import type { PipelineChapter, PipelineStage } from '../../types/plan';
import type { UsePlanPipelineResult } from './usePlanPipeline';

const { TextArea } = Input;

const stageText: Record<PipelineStage, string> = {
  idle: '等待输入',
  basic_info: '正在获取基本信息',
  template_split: '正在切分模板',
  parallel_generating: '正在并行生成章节',
  case_search: '正在检索案例',
  done: '生成完成',
  error: '生成失败'
};

const chapterStatusText: Record<'pending' | 'running' | 'done' | 'error', string> = {
  pending: '等待中',
  running: '生成中',
  done: '已完成',
  error: '失败'
};

type PlanPageProps = {
  plan: UsePlanPipelineResult;
  showModeTags: boolean;
  showCompactLayout: boolean;
};

export function PlanPage({ plan, showModeTags, showCompactLayout }: PlanPageProps) {
  const renderPresetPopover = () => {
    const { Text, Title } = Typography;
    return (
      <div className="preset-popover__content">
        <div className="preset-popover__group preset-popover__group--single">
          <div className="preset-popover__heading">
            <span className="preset-popover__badge preset-popover__badge--single">单故障</span>
            <div className="preset-popover__heading-copy">
              <Title level={5} className="preset-popover__title">常规单故障问题</Title>
              <Typography.Text className="preset-popover__desc">适合单一主故障场景，生成链路更直接。</Typography.Text>
            </div>
          </div>
          {DEVICE_QUESTIONS.map((device) => (
            <div key={`single-${device.device}`} className="preset-popover__section">
              <Text strong className="preset-popover__device preset-popover__device--single">{device.device}</Text>
              {device.singleFault.map((question, index) => (
                <div
                  key={index}
                  className="preset-item"
                  onClick={() => plan.pickQuestion(question)}
                >
                  {question.length > 60 ? `${question.substring(0, 60)}…` : question}
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="preset-popover__group preset-popover__group--multi">
          <div className="preset-popover__heading">
            <span className="preset-popover__badge preset-popover__badge--multi">多故障</span>
            <div className="preset-popover__heading-copy">
              <Title level={5} className="preset-popover__title">常规多故障问题</Title>
              <Typography.Text className="preset-popover__desc">适合并发或伴随故障场景，会触发多故障检索思路。</Typography.Text>
            </div>
          </div>
          {DEVICE_QUESTIONS.map((device) => (
            <div key={`multi-${device.device}`} className="preset-popover__section">
              <Text strong className="preset-popover__device preset-popover__device--multi">{device.device}</Text>
              {device.multiFault.map((question, index) => (
                <div
                  key={index}
                  className="preset-item"
                  onClick={() => plan.pickQuestion(question)}
                >
                  {question.length > 60 ? `${question.substring(0, 60)}…` : question}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="pipeline-page">
      <Card title="故障场景输入" className="panel-card pipeline-input-card">
        <TextArea
          value={plan.question}
          onChange={(event) => plan.setQuestion(event.target.value)}
          autoSize={{ minRows: 2, maxRows: 4 }}
          placeholder="请输入故障问题或场景，例如：暴雨导致电缆沟进水..."
        />
        <Space className="action-row" wrap>
          <Button type="primary" icon={<PlayCircleOutlined />} loading={plan.loading} onClick={plan.handleGenerate}>
            运行流水线
          </Button>
          <Popover
            content={renderPresetPopover()}
            trigger="click"
            open={plan.questionPopoverOpen}
            onOpenChange={plan.setQuestionPopoverOpen}
            placement="bottomLeft"
            destroyTooltipOnHide
            overlayClassName="preset-popover"
          >
            <Button>填入示例</Button>
          </Popover>
          <Button size="small" icon={<CopyOutlined />} disabled={!plan.chapters.length} onClick={plan.handleCopy}>
            复制全部
          </Button>
          <Button size="small" icon={<DownloadOutlined />} disabled={!plan.chapters.length} onClick={plan.handleDownload}>
            下载全部
          </Button>
          <Checkbox
            className="action-toggle"
            checked={plan.enableCaseSearch}
            onChange={(event) => plan.setEnableCaseSearch(event.target.checked)}
          >
            开启案例搜索
          </Checkbox>
          <Checkbox
            className="action-toggle"
            checked={plan.enableMultiFaultSearch}
            onChange={(event) => plan.setEnableMultiFaultSearch(event.target.checked)}
          >
            开启多故障检索
          </Checkbox>
        </Space>
        <div className="status-box">
          <Tag color={plan.stage === 'error' ? 'red' : plan.stage === 'done' ? 'green' : 'processing'}>
            {stageText[plan.stage]}
          </Tag>
          <Tag>{plan.nodeStageLabel}</Tag>
          {plan.savedFlag ? <Tag color="success">已保存</Tag> : null}
          {plan.summaryTags.map((tag) => (
            <Tag color="purple" key={tag}>
              {tag}
            </Tag>
          ))}
        </div>
      </Card>

      <div
        className="chapter-row"
        style={
          plan.chapters.length
            ? {
                gridTemplateColumns: showCompactLayout
                  ? 'repeat(3, minmax(0, 1fr))'
                  : `repeat(${plan.chapters.length}, minmax(0, 1fr))`
              }
            : undefined
        }
      >
        {plan.chapters.length ? (
          plan.chapters.map((chapter: PipelineChapter) => (
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
    </div>
  );
}
