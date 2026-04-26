import { Button, Card, Checkbox, Input, Popover, Space, Tag } from 'antd';
import { CopyOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { PipelineStage } from '../../types/plan';
import type { UsePlanPipelineResult } from './usePlanPipeline';
import { PresetQuestionPopover } from './PresetQuestionPopover';

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

type PlanInputCardProps = {
  plan: UsePlanPipelineResult;
};

export function PlanInputCard({ plan }: PlanInputCardProps) {
  return (
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
          content={<PresetQuestionPopover onPickQuestion={plan.pickQuestion} />}
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
  );
}
