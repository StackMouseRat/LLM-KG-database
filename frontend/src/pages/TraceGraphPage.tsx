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
  if (node.type === 'root_node') {
    return [164, 52];
  }
  if (node.type === 'fault_l1') {
    return [92, 52];
  }
  if (node.type === 'fault_l2') {
    return [83, 49];
  }
  return [48, 45];
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

function buildL1Groups(trace: PlanTrace) {
  const visibleNodes = trace.graph.nodes.filter((node) => node.type === 'fault_l1' || node.type === 'fault_l2');
  const nodeMap = new Map(visibleNodes.map((node) => [node.id, node]));
  const l1Nodes = visibleNodes.filter((node): node is TraceNode => node.type === 'fault_l1');

  const l2ByL1 = new Map<string, TraceNode[]>();
  for (const edge of trace.graph.edges) {
    if (edge.label !== '包含') continue;
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (source?.type === 'fault_l1' && target?.type === 'fault_l2') {
      const list = l2ByL1.get(source.id) || [];
      list.push(target);
      l2ByL1.set(source.id, list);
    }
  }

  const remaining = l1Nodes.map((l1Node) => ({
    l1Node,
    l2Nodes: l2ByL1.get(l1Node.id) || []
  }));

  const groups: Array<{ members: Array<{ l1Node: TraceNode; l2Nodes: TraceNode[] }>; totalL2: number }> = [];

  while (remaining.length > 0) {
    remaining.sort((a, b) => b.l2Nodes.length - a.l2Nodes.length);
    const current = remaining.shift();
    if (!current) break;
    if (remaining.length === 0) {
      groups.push({ members: [current], totalL2: current.l2Nodes.length });
      break;
    }

    let bestIndex = 0;
    let bestDiff = Number.POSITIVE_INFINITY;
    for (let index = 0; index < remaining.length; index += 1) {
      const diff = Math.abs(current.l2Nodes.length - remaining[index].l2Nodes.length);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestIndex = index;
      }
    }

    const pair = remaining.splice(bestIndex, 1)[0];
    groups.push({
      members: [current, pair],
      totalL2: current.l2Nodes.length + pair.l2Nodes.length
    });
  }

  return groups;
}

function getDisplayLabel(node: TraceNode, focusFaultName: string) {
  if (node.type === 'fault_l2' || node.type === 'fault_l1' || node.type === 'root_node') {
    return node.label;
  }
  let label = node.label;
  if (focusFaultName) {
    const focusPrefix = `${focusFaultName}-`;
    if (label.startsWith(focusPrefix)) {
      label = label.slice(focusPrefix.length);
    }
  }
  const splitIndex = label.indexOf('-');
  if (splitIndex > 0 && splitIndex < label.length - 1) {
    label = label.slice(splitIndex + 1);
  }
  if (label.length === 4) {
    return `${label.slice(0, 2)}\n${label.slice(2)}`;
  }
  return label;
}

function computeSnowflakeLayout(trace: PlanTrace, width: number, height: number) {
  const centerX = width / 2;
  const centerY = height / 2;
  const positions: Record<string, { x: number; y: number }> = {};
  const visibleNodeIds = new Set<string>();

  const root = trace.graph.nodes.find((node) => node.type === 'root_node') || trace.graph.nodes[0];
  if (!root) return { positions, visibleNodeIds };
  positions[root.id] = { x: centerX, y: centerY };
  visibleNodeIds.add(root.id);

  const allNodes = trace.graph.nodes;
  const allEdges = trace.graph.edges;
  const nodeMap = new Map(allNodes.map((node) => [node.id, node]));
  const outgoing = new Map<string, string[]>();

  for (const edge of allEdges) {
    const list = outgoing.get(edge.source) || [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }

  const level1 = allNodes.filter((node): node is TraceNode => node.type === 'fault_l1');
  const level2 = allNodes.filter((node): node is TraceNode => node.type === 'fault_l2');

  const level3Ids = new Set<string>();
  for (const node of level2) {
    for (const targetId of outgoing.get(node.id) || []) {
      level3Ids.add(targetId);
    }
  }

  const level4Ids = new Set<string>();
  for (const nodeId of level3Ids) {
    for (const targetId of outgoing.get(nodeId) || []) {
      level4Ids.add(targetId);
    }
  }

  const level3 = [...level3Ids]
    .map((id) => nodeMap.get(id))
    .filter((node): node is TraceNode => Boolean(node));
  const level4 = [...level4Ids]
    .map((id) => nodeMap.get(id))
    .filter((node): node is TraceNode => Boolean(node));

  const fullCircle = Math.PI * 2;
  const ringConfigs: Array<{ nodes: TraceNode[]; radius: number }> = [
    { nodes: level1, radius: 180 },
    { nodes: level2, radius: 540 },
    { nodes: level3, radius: 760 },
    { nodes: level4, radius: 980 }
  ];

  ringConfigs.forEach(({ nodes, radius }) => {
    nodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + ((index + 0.5) * fullCircle) / Math.max(1, nodes.length);
      positions[node.id] = polarToCartesian(centerX, centerY, radius, angle);
      visibleNodeIds.add(node.id);
    });
  });

  return { positions, visibleNodeIds };
}

export function TraceGraphPage({ pipeline, darkMode }: TraceGraphPageProps) {
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<any>(null);
  const [trace, setTrace] = useState<PlanTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [graphViewport, setGraphViewport] = useState({ width: 1680, height: 1080 });

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
      const layoutResult = computeSnowflakeLayout(trace, width, height);
      const nodePositions = layoutResult.positions;
      const visibleNodeIds = layoutResult.visibleNodeIds;
      setGraphViewport({ width, height });

      const graphData: any = {
        nodes: trace.graph.nodes
          .filter((node) => visibleNodeIds.has(node.id))
          .map((node) => ({
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
      edges: trace.graph.edges
        .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
        .map((edge) => ({
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
            labelMaxWidth: (d: any) => (Array.isArray(d.data?.size) ? d.data.size[0] - (d.data?.type === 'fault_l2' ? 12 : 4) : 150),
            labelMaxLines: (d: any) => (d.data?.type === 'fault_l2' || d.data?.type === 'fault_l1' ? 5 : 2),
            fontSize: (d: any) => (d.data?.type === 'fault_l2' ? 10 : d.data?.type === 'root_node' || d.data?.type === 'fault_l1' ? 12 : 9)
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
        <div className="trace-graph-container">
          <div className="trace-graph-canvas" ref={graphContainerRef} />
        </div>
      </Card>
    </div>
  );
}
