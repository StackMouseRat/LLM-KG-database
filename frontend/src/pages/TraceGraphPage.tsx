import { Card, Empty, Tag, Typography } from 'antd';
import type { PlanTrace } from '../types/plan';

interface TraceGraphPageProps {
  trace: PlanTrace | null;
}

export function TraceGraphPage({ trace }: TraceGraphPageProps) {
  if (!trace) {
    return (
      <div className="pipeline-page">
        <Card title="图谱溯源" className="panel-card pipeline-input-card">
          <Typography.Paragraph className="app-subtitle">
            当前页面为图谱溯源入口页，后续将在这里展示预案生成过程中的知识命中、节点关系与图谱证据。
          </Typography.Paragraph>
          <div className="status-box">
            <Tag color="cyan">占位页</Tag>
            <Tag>待接入图谱溯源可视化结果</Tag>
          </div>
        </Card>
        <Card title="图谱溯源占位" className="panel-card chapter-empty-card">
          <Empty description="请先生成一份预案，再查看溯源分析" />
        </Card>
      </div>
    );
  }

  return (
    <div className="trace-grid">
      <Card title="本次识别结果" className="panel-card">
        <p>
          <Typography.Text strong>设备空间：</Typography.Text>
          <Tag color="blue">{trace.device || '未识别'}</Tag>
        </p>
        <p>
          <Typography.Text strong>匹配故障：</Typography.Text>
          <Tag color="purple">{trace.fault || '未识别'}</Tag>
        </p>
        <p>
          <Typography.Text strong>图谱节点数：</Typography.Text>
          {trace.graph.nodes.length}
        </p>
      </Card>
      <Card title="图谱溯源占位" className="panel-card trace-card">
        <Empty description="G6 图谱将在下一步接入。当前已保留 trace.graph 数据结构。" />
        <pre className="trace-json">{JSON.stringify(trace.graph.nodes.slice(0, 8), null, 2)}</pre>
      </Card>
    </div>
  );
}
