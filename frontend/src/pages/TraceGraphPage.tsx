import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, Empty, Spin, Tag, Typography } from 'antd';
import { fetchTraceSubgraph } from '../services/planApi';
import type { PipelineRunResponse, PlanTrace, TraceNode } from '../types/plan';

interface TraceGraphPageProps {
  pipeline: PipelineRunResponse | null;
  darkMode: boolean;
}

const NODE_COLOR_MAP: Record<TraceNode['type'], string> = {
  root_node: '#0f766e',
  fault_l1: '#2563eb',
  fault_l2: '#dc2626',
  fault_cause: '#f97316',
  fault_symptom: '#0ea5e9',
  response_measure: '#16a34a',
  fault_consequence: '#ef4444',
  safety_risk: '#7c3aed',
  emergency_resource: '#14b8a6',
  unknown: '#64748b'
};

function getNodeSize(node: TraceNode): [number, number] {
  if (node.type === 'root_node' || node.type === 'fault_l1') {
    return [164, 52];
  }
  if (node.type === 'fault_l2') {
    return [220, 86];
  }
  return [82, 26];
}

function polarToCartesian(cx: number, cy: number, radius: number, angle: number) {
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle)
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function getDisplayLabel(node: TraceNode, focusFaultName: string) {
  if (node.type === 'fault_l2' || node.type === 'fault_l1' || node.type === 'root_node') {
    return node.label;
  }
  if (focusFaultName) {
    const focusPrefix = `${focusFaultName}-`;
    if (node.label.startsWith(focusPrefix)) {
      return node.label.slice(focusPrefix.length);
    }
  }
  const splitIndex = node.label.indexOf('-');
  if (splitIndex > 0 && splitIndex < node.label.length - 1) {
    return node.label.slice(splitIndex + 1);
  }
  return node.label;
}

function computeSnowflakeLayout(trace: PlanTrace, width: number, height: number) {
  const centerX = width / 2;
  const centerY = height / 2;
  const positions: Record<string, { x: number; y: number }> = {};
  const nodeMap = new Map(trace.graph.nodes.map((node) => [node.id, node]));
  const outgoing = new Map<string, Array<{ target: string; label: string }>>();

  for (const edge of trace.graph.edges) {
    const list = outgoing.get(edge.source) || [];
    list.push({ target: edge.target, label: edge.label });
    outgoing.set(edge.source, list);
  }

  const root = trace.graph.nodes.find((node) => node.type === 'root_node') || trace.graph.nodes[0];
  if (!root) return positions;
  positions[root.id] = { x: centerX, y: centerY };

  const l1Nodes = (outgoing.get(root.id) || [])
    .map((item) => nodeMap.get(item.target))
    .filter((item): item is TraceNode => Boolean(item && item.type === 'fault_l1'));

  const fullCircle = Math.PI * 2;
  const l1Radius = 240;
  const l2BaseRadius = 440;
  const l2RadiusStep = 44;
  const childOffsetRadius = 190;
  const grandchildOffsetRadius = 135;

  const l1Groups = l1Nodes.map((l1Node) => ({
    l1Node,
    l2Nodes: (outgoing.get(l1Node.id) || [])
      .map((item) => nodeMap.get(item.target))
      .filter((item): item is TraceNode => Boolean(item && item.type === 'fault_l2'))
  }));

  const totalSectorCount = Math.max(
    1,
    l1Groups.reduce((sum, group) => sum + Math.max(1, group.l2Nodes.length), 0)
  );
  const sectorAngle = fullCircle / totalSectorCount;
  let sectorCursor = 0;

  l1Groups.forEach(({ l1Node, l2Nodes }) => {
    const sectorCount = Math.max(1, l2Nodes.length);
    const firstSectorCenter = -Math.PI / 2 + (sectorCursor + 0.5) * sectorAngle;
    const lastSectorCenter = -Math.PI / 2 + (sectorCursor + sectorCount - 0.5) * sectorAngle;
    const l1Angle = (firstSectorCenter + lastSectorCenter) / 2;

    positions[l1Node.id] = polarToCartesian(centerX, centerY, l1Radius, l1Angle);

    l2Nodes.forEach((l2Node, index) => {
      const sectorCenter = -Math.PI / 2 + (sectorCursor + index + 0.5) * sectorAngle;
      const sectorStart = sectorCenter - sectorAngle / 2;
      const sectorEnd = sectorCenter + sectorAngle / 2;
      const usableSectorStart = sectorStart + sectorAngle * 0.12;
      const usableSectorEnd = sectorEnd - sectorAngle * 0.12;

      const spiralIndex = sectorCursor + index;
      const l2Radius = l2BaseRadius + spiralIndex * l2RadiusStep;
      positions[l2Node.id] = polarToCartesian(centerX, centerY, l2Radius, sectorCenter);

      const children = (outgoing.get(l2Node.id) || [])
        .map((item) => ({ edge: item, node: nodeMap.get(item.target) }))
        .filter((item): item is { edge: { target: string; label: string }; node: TraceNode } => Boolean(item.node));

      const childAngles: number[] = [];
      children.forEach((child, childIndex) => {
        const childAngle =
          children.length === 1
            ? sectorCenter
            : usableSectorStart +
              ((usableSectorEnd - usableSectorStart) * childIndex) / Math.max(1, children.length - 1);
        childAngles.push(childAngle);
        const childRadius = l2Radius + childOffsetRadius;
        positions[child.node.id] = polarToCartesian(centerX, centerY, childRadius, childAngle);

        const grandchildren = (outgoing.get(child.node.id) || [])
          .map((item) => nodeMap.get(item.target))
          .filter((item): item is TraceNode => Boolean(item));

          const childSpan = Math.min((usableSectorEnd - usableSectorStart) / Math.max(1, children.length), sectorAngle * 0.42);
          grandchildren.forEach((grandchild, grandchildIndex) => {
            const grandchildAngle =
              grandchildren.length === 1
                ? childAngle
                : childAngle - childSpan / 2 + (childSpan * grandchildIndex) / Math.max(1, grandchildren.length - 1);
            const grandchildRadius = childRadius + grandchildOffsetRadius;
            positions[grandchild.id] = polarToCartesian(
              centerX,
              centerY,
              grandchildRadius,
              clamp(grandchildAngle, usableSectorStart, usableSectorEnd)
            );
          });
      });
    });

    sectorCursor += sectorCount;
  });

  let fallbackIndex = 0;
  for (const node of trace.graph.nodes) {
    if (positions[node.id]) continue;
    const angle = -Math.PI / 2 + (fullCircle * fallbackIndex) / Math.max(1, trace.graph.nodes.length);
    const fallbackRadius =
      l2BaseRadius + totalSectorCount * l2RadiusStep + childOffsetRadius + grandchildOffsetRadius + 180;
    positions[node.id] = polarToCartesian(centerX, centerY, fallbackRadius, angle);
    fallbackIndex += 1;
  }

  return positions;
}

export function TraceGraphPage({ pipeline, darkMode }: TraceGraphPageProps) {
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<any>(null);
  const [trace, setTrace] = useState<PlanTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('');

  useEffect(() => {
    if (!pipeline) {
      setTrace(null);
      setSelectedNodeId('');
      setErrorText('');
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorText('');

    void fetchTraceSubgraph({
      question: pipeline.question,
      faultScene: pipeline.basicInfo.faultScene,
      graphMaterial: pipeline.basicInfo.graphMaterial
    })
      .then((nextTrace) => {
        if (cancelled) return;
        setTrace(nextTrace);
        const focusNode = nextTrace.graph.nodes.find((node) => node.isFocus) || nextTrace.graph.nodes[0];
        setSelectedNodeId(focusNode?.id || '');
      })
      .catch((error) => {
        if (cancelled) return;
        setTrace(null);
        setSelectedNodeId('');
        setErrorText(error instanceof Error ? error.message : '图谱溯源加载失败');
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pipeline]);

  const selectedNode = useMemo(
    () => trace?.graph.nodes.find((node) => node.id === selectedNodeId) || null,
    [trace, selectedNodeId]
  );
  const hitNodeCount = useMemo(
    () => trace?.graph.nodes.filter((node) => node.isHit || node.isFocus).length || 0,
    [trace]
  );

  useEffect(() => {
    if (!graphContainerRef.current) return;
    if (!trace?.graph?.nodes?.length) return;
    let cancelled = false;
    let currentGraph: any = null;

    void import('@antv/g6').then(async ({ Graph }) => {
      if (cancelled || !graphContainerRef.current) return;
      const width = graphContainerRef.current.clientWidth || 1680;
      const height = graphContainerRef.current.clientHeight || 1080;
      const nodePositions = computeSnowflakeLayout(trace, width, height);

      const graphData: any = {
        nodes: trace.graph.nodes.map((node) => ({
          id: node.id,
          data: {
            label: node.label,
            displayLabel: (node as any).wrappedLabel || getDisplayLabel(node, trace.fault || ''),
            desc: node.desc,
            type: node.type,
            isFocus: Boolean(node.isFocus),
            isHit: Boolean(node.isHit),
            size: getNodeSize(node),
            borderColor: NODE_COLOR_MAP[node.type] || NODE_COLOR_MAP.unknown,
            stroke: node.isFocus
              ? '#0f172a'
              : node.isHit
                ? NODE_COLOR_MAP[node.type] || NODE_COLOR_MAP.unknown
                : darkMode
                  ? '#475569'
                  : '#cbd5e1',
            lineWidth: node.isFocus ? 3 : node.isHit ? 2.4 : 1.4,
            labelColor: node.isHit || node.isFocus ? (darkMode ? '#f8fafc' : '#0f172a') : darkMode ? '#94a3b8' : '#64748b'
          },
          style: {
            x: nodePositions[node.id]?.x,
            y: nodePositions[node.id]?.y
          }
        })),
      edges: trace.graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        data: {
          label: edge.label,
          isHit: Boolean(edge.isHit),
          stroke: edge.isHit ? (darkMode ? '#94a3b8' : '#64748b') : darkMode ? '#334155' : '#cbd5e1'
        }
      }))
      };

      const graph = new Graph({
        container: graphContainerRef.current,
        width,
        height,
        autoFit: 'center',
        data: graphData,
        node: {
          type: 'rect',
          style: {
            radius: 12,
            size: (d: any) => d.data?.size || [164, 52],
            fill: '#ffffff',
            fillOpacity: 0,
            stroke: (d: any) => d.data?.stroke,
            lineWidth: (d: any) => d.data?.lineWidth,
            labelText: (d: any) => d.data?.displayLabel || d.data?.label,
            labelPlacement: 'center',
            labelTextAlign: 'center',
            labelTextBaseline: 'middle',
            labelFill: (d: any) => d.data?.labelColor,
            labelWordWrap: true,
            labelMaxWidth: (d: any) => (Array.isArray(d.data?.size) ? d.data.size[0] - 20 : 150),
            labelMaxLines: (d: any) => (d.data?.type === 'fault_l2' ? 2 : 1),
            fontSize: (d: any) => (d.data?.type === 'fault_l2' ? 11 : d.data?.type === 'root_node' || d.data?.type === 'fault_l1' ? 12 : 10)
          }
        } as any,
        edge: {
          type: 'line',
          style: {
            stroke: (d: any) => d.data?.stroke || '#94a3b8',
            lineWidth: (d: any) => (d.data?.isHit ? 1.8 : 1.1),
            startArrow: false,
            endArrow: true,
            endArrowType: 'vee',
            endArrowFill: (d: any) => d.data?.stroke || (darkMode ? '#94a3b8' : '#64748b'),
            endArrowOffset: 0,
            labelText: (d: any) => d.data?.label,
            labelFill: (d: any) => (d.data?.isHit ? (darkMode ? '#f8fafc' : '#334155') : darkMode ? '#94a3b8' : '#64748b'),
            labelBackground: true,
            labelBackgroundFill: darkMode ? '#0f172a' : '#ffffff',
            labelOpacity: (d: any) => (d.data?.isHit ? 1 : 0.78),
            opacity: (d: any) => (d.data?.isHit ? 1 : 0.72)
          }
        } as any,
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'] as any
      });

      graph.on('node:click', (event: any) => {
        const nextId = String(event?.target?.id || '');
        if (nextId) {
          setSelectedNodeId(nextId);
        }
      });

      await graph.render();
      if (cancelled) {
        graph.destroy();
        return;
      }
      currentGraph = graph;
      graphRef.current = graph;
    });

    return () => {
      cancelled = true;
      if (currentGraph) {
        currentGraph.destroy();
      }
      graphRef.current = null;
    };
  }, [trace, darkMode]);

  if (!pipeline) {
    return (
      <div className="pipeline-page">
        <Card title="图谱溯源" className="panel-card pipeline-input-card">
          <Typography.Paragraph className="app-subtitle">
            请先生成一份预案，再查看本次故障对应的图谱溯源子图。
          </Typography.Paragraph>
        </Card>
        <Card title="图谱溯源" className="panel-card chapter-empty-card">
          <Empty description="当前没有可供展示的预案结果" />
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="pipeline-page">
        <Card title="图谱溯源" className="panel-card chapter-empty-card trace-loading-card">
          <Spin tip="正在生成当前故障的图谱溯源子图..." />
        </Card>
      </div>
    );
  }

  if (errorText) {
    return (
      <div className="pipeline-page">
        <Card title="图谱溯源" className="panel-card pipeline-input-card">
          <Typography.Paragraph className="app-subtitle">
            当前根据本次生成结果提取设备根节点与二级故障名称，并向 Nebula 查询上游链路和全部下游节点。
          </Typography.Paragraph>
          <div className="status-box">
            <Tag color="red">加载失败</Tag>
            <Tag>{errorText}</Tag>
          </div>
        </Card>
      </div>
    );
  }

  if (!trace || !trace.graph.nodes.length) {
    return (
      <div className="pipeline-page">
        <Card title="图谱溯源" className="panel-card chapter-empty-card">
          <Empty description="未查询到对应的图谱溯源子图" />
        </Card>
      </div>
    );
  }

  return (
    <div className="trace-grid">
      <div className="trace-side-column">
        <Card title="本次识别结果" className="panel-card trace-card">
          <p>
            <Typography.Text strong>设备根节点：</Typography.Text>
            <Tag color="blue">{trace.device || '未识别'}</Tag>
          </p>
          <p>
            <Typography.Text strong>当前二级故障：</Typography.Text>
            <Tag color="red">{trace.fault || '未识别'}</Tag>
          </p>
          <p>
            <Typography.Text strong>图谱节点数：</Typography.Text>
            {trace.graph.nodes.length}
          </p>
          <p>
            <Typography.Text strong>关系边数：</Typography.Text>
            {trace.graph.edges.length}
          </p>
          <p>
            <Typography.Text strong>命中节点数：</Typography.Text>
            {hitNodeCount}
          </p>
        </Card>

        <Card title="节点详情" className="panel-card trace-card">
          {selectedNode ? (
            <>
              <p>
                <Typography.Text strong>节点名称：</Typography.Text>
                {selectedNode.label}
              </p>
              <p>
                <Typography.Text strong>节点类型：</Typography.Text>
                <Tag color="purple">{selectedNode.type}</Tag>
              </p>
              <p>
                <Typography.Text strong>节点描述：</Typography.Text>
              </p>
              <div className="trace-node-desc">{selectedNode.desc || '暂无描述'}</div>
            </>
          ) : (
            <Empty description="点击图中的节点查看详情" />
          )}
        </Card>
      </div>

      <Card title="图谱溯源可视化" className="panel-card trace-card trace-graph-card">
        <div className="trace-graph-container" ref={graphContainerRef} />
      </Card>
    </div>
  );
}
