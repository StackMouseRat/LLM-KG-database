import { Card, Empty, Tag, Typography } from 'antd';
import type { PlanTrace } from '../types/plan';

interface TraceGraphPageProps {
  trace: PlanTrace | null;
}

export function TraceGraphPage({ trace }: TraceGraphPageProps) {
  if (!trace) {
    return <Empty description="请先生成一份预案，再查看溯源分析" />;
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
