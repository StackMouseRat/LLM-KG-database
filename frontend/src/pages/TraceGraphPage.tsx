import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, Empty, Spin, Tag, Typography } from 'antd';
import { fetchTraceSubgraph } from '../services/planApi';
import type { PipelineRunResponse, PlanTrace, TraceNode } from '../types/plan';
import { buildTraceAnimationSeedData } from './traceGraphScene';
import { buildTraceAnimationPlans, createTraceAnimationController } from './traceGraphAnimation';

interface TraceGraphPageProps {
  pipeline: PipelineRunResponse | null;
  darkMode: boolean;
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
  const hitFaultNodes = useMemo(
    () =>
      trace?.graph.nodes.filter((node) => node.type === 'fault_l2' && (node.isHit || node.isFocus)).map((node) => node.label) ||
      [],
    [trace]
  );

  useEffect(() => {
    if (!graphContainerRef.current) return;
    if (!trace?.graph?.nodes?.length) return;
    let cancelled = false;
    let currentGraph: any = null;
    let animationController: { start: () => Promise<void>; stop: () => void } | null = null;

    void import('@antv/g6').then(async ({ Graph }) => {
      if (cancelled || !graphContainerRef.current) return;
      const width = graphContainerRef.current.clientWidth || 1680;
      const height = graphContainerRef.current.clientHeight || 1080;
      const { rootId } = buildTraceAnimationPlans(trace);
      const graphData = buildTraceAnimationSeedData(trace, darkMode, width, height, rootId);
      setGraphViewport({ width, height });

      const graph = new Graph({
        container: graphContainerRef.current,
        width,
        height,
        autoFit: 'center',
        data: graphData,
        animation: false,
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
            labelOpacity: (d: any) => d.data?.labelOpacity ?? (d.data?.isHit ? 1 : 0.78),
            opacity: (d: any) => d.data?.strokeOpacity ?? (d.data?.isHit ? 1 : 0.72)
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
      animationController = createTraceAnimationController({
        trace,
        graph,
        darkMode,
        width,
        height
      });
      void animationController.start();
    });

    return () => {
      cancelled = true;
      animationController?.stop();
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
            <Typography.Text strong>主故障二级节点：</Typography.Text>
            <Tag color="red">{trace.fault || '未识别'}</Tag>
          </p>
          <p>
            <Typography.Text strong>命中二级故障：</Typography.Text>
            {hitFaultNodes.length ? (
              hitFaultNodes.map((fault) => (
                <Tag color={fault === trace.fault ? 'red' : 'purple'} key={fault}>
                  {fault}
                </Tag>
              ))
            ) : (
              <Tag>未识别</Tag>
            )}
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
