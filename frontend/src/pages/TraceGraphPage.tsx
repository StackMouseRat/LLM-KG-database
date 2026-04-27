import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Empty, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import {
  buildTraceCacheSignature,
  loadTraceCache,
  markTraceAnimationPlayed,
  saveTraceCache,
  saveTraceViewport,
  type TraceViewport
} from '../features/trace/traceCache';
import { fetchTraceSubgraph } from '../services/planApi';
import type { PipelineRunResponse, PlanTrace, TraceNode } from '../types/plan';
import { buildTraceAnimationSeedData, buildTraceGraphData } from './traceGraphScene';
import { buildTraceAnimationPlans, createTraceAnimationController } from './traceGraphAnimation';

interface TraceGraphPageProps {
  pipeline: PipelineRunResponse | null;
  darkMode: boolean;
}

function readGraphViewport(graph: any): TraceViewport | null {
  if (!graph) return null;
  try {
    const rawPosition = graph.getPosition?.();
    const position: [number, number] = Array.isArray(rawPosition)
      ? [Number(rawPosition[0] || 0), Number(rawPosition[1] || 0)]
      : [Number(rawPosition?.x || 0), Number(rawPosition?.y || 0)];
    return {
      zoom: Number(graph.getZoom?.() || 1),
      position,
      rotation: typeof graph.getRotation === 'function' ? Number(graph.getRotation() || 0) : undefined
    };
  } catch {
    return null;
  }
}

async function restoreGraphViewport(graph: any, viewport?: TraceViewport) {
  if (!graph || !viewport) return;
  if (typeof viewport.rotation === 'number' && typeof graph.rotateTo === 'function') {
    await graph.rotateTo(viewport.rotation);
  }
  if (typeof graph.zoomTo === 'function') {
    await graph.zoomTo(viewport.zoom || 1);
  }
  if (typeof graph.translateTo === 'function') {
    await graph.translateTo(viewport.position);
  }
}

export function TraceGraphPage({ pipeline, darkMode }: TraceGraphPageProps) {
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<any>(null);
  const animationCompletedRef = useRef(false);
  const [trace, setTrace] = useState<PlanTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [errorText, setErrorText] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [shouldPlayAnimation, setShouldPlayAnimation] = useState(false);
  const [animationNonce, setAnimationNonce] = useState(0);
  const [graphReady, setGraphReady] = useState(false);
  const [graphViewport, setGraphViewport] = useState({ width: 1680, height: 1080 });
  const traceSignature = useMemo(() => buildTraceCacheSignature(pipeline), [pipeline]);

  const selectDefaultNode = useCallback((nextTrace: PlanTrace) => {
    const focusNode = nextTrace.graph.nodes.find((node) => node.isFocus) || nextTrace.graph.nodes[0];
    setSelectedNodeId(focusNode?.id || '');
  }, []);

  const loadTraceData = useCallback(
    async (forceRefresh = false) => {
      if (!pipeline || !traceSignature) {
        setTrace(null);
        setSelectedNodeId('');
        setErrorText('');
        setShouldPlayAnimation(false);
        setGraphReady(false);
        return;
      }

      if (!forceRefresh) {
        const cached = loadTraceCache(traceSignature);
        if (cached?.trace) {
          setTrace(cached.trace);
          selectDefaultNode(cached.trace);
          setErrorText('');
          animationCompletedRef.current = Boolean(cached.animationPlayed);
          setShouldPlayAnimation(!cached.animationPlayed);
          setAnimationNonce((value) => value + 1);
          setLoading(false);
          return;
        }
      }

      if (forceRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setErrorText('');

      try {
        const nextTrace = await fetchTraceSubgraph({
          question: pipeline.question,
          faultScene: pipeline.basicInfo.faultScene,
          graphMaterial: pipeline.basicInfo.graphMaterial
        });
        saveTraceCache(traceSignature, nextTrace, false);
        animationCompletedRef.current = false;
        setTrace(nextTrace);
        selectDefaultNode(nextTrace);
        setShouldPlayAnimation(true);
        setAnimationNonce((value) => value + 1);
      } catch (error) {
        setTrace(null);
        setSelectedNodeId('');
        animationCompletedRef.current = false;
        setShouldPlayAnimation(false);
        setGraphReady(false);
        setErrorText(error instanceof Error ? error.message : '图谱溯源加载失败');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [pipeline, selectDefaultNode, traceSignature]
  );

  useEffect(() => {
    if (!pipeline) {
      setTrace(null);
      setSelectedNodeId('');
      setErrorText('');
      setShouldPlayAnimation(false);
      setGraphReady(false);
      return;
    }

    void loadTraceData(false);
  }, [loadTraceData, pipeline]);

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
    const playAnimation = shouldPlayAnimation && !animationCompletedRef.current;
    setGraphReady(false);
    let cancelled = false;
    let currentGraph: any = null;
    let animationController: { start: () => Promise<void>; stop: () => void } | null = null;

    const persistCurrentViewport = () => {
      const viewport = readGraphViewport(currentGraph || graphRef.current);
      if (!viewport) return;
      saveTraceViewport(traceSignature, viewport);
    };

    void import('@antv/g6').then(async ({ Graph }) => {
      if (cancelled || !graphContainerRef.current) return;
      const width = graphContainerRef.current.clientWidth || 1680;
      const height = graphContainerRef.current.clientHeight || 1080;
      const { rootId } = buildTraceAnimationPlans(trace);
      const graphData = playAnimation
        ? buildTraceAnimationSeedData(trace, darkMode, width, height, rootId)
        : buildTraceGraphData(trace, darkMode, width, height).graphData;
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
      graph.on('aftertransform', persistCurrentViewport);

      await graph.render();
      if (cancelled) {
        graph.destroy();
        return;
      }
      currentGraph = graph;
      graphRef.current = graph;
      if (!playAnimation) {
        await restoreGraphViewport(graph, loadTraceCache(traceSignature)?.viewport);
      }
      window.requestAnimationFrame(() => {
        if (!cancelled) setGraphReady(true);
      });
      if (playAnimation) {
        animationController = createTraceAnimationController({
          trace,
          graph,
          darkMode,
          width,
          height
        });
        void animationController.start().then(() => {
          if (cancelled) return;
          animationCompletedRef.current = true;
          markTraceAnimationPlayed(traceSignature);
        });
      }
    });

    return () => {
      cancelled = true;
      persistCurrentViewport();
      animationController?.stop();
      if (currentGraph) {
        currentGraph.destroy();
      }
      graphRef.current = null;
    };
  }, [trace, darkMode, shouldPlayAnimation, animationNonce, traceSignature]);

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
        <Card
          title="本次识别结果"
          className="panel-card trace-card"
          extra={
            <Button size="small" icon={<ReloadOutlined />} loading={refreshing} onClick={() => void loadTraceData(true)}>
              刷新
            </Button>
          }
        >
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
          <div className={`trace-graph-canvas ${graphReady ? 'trace-graph-canvas--ready' : ''}`} ref={graphContainerRef} />
        </div>
      </Card>
    </div>
  );
}
