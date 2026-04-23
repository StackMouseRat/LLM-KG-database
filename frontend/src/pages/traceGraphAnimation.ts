import type { PlanTrace, TraceEdge, TraceNode } from '../types/plan';
import { buildVisibleTraceGraphData } from './traceGraphScene';

type BranchPlan = {
  l1Id: string;
  edgeLevels: string[][];
  nodeLevels: string[][];
};

function filterPlan(plan: BranchPlan | null, excludedNodeIds: Set<string>, excludedEdgeIds: Set<string>) {
  if (!plan) return null;
  return {
    l1Id: plan.l1Id,
    edgeLevels: plan.edgeLevels.map((level) => level.filter((id) => !excludedEdgeIds.has(id))),
    nodeLevels: plan.nodeLevels.map((level) => level.filter((id) => !excludedNodeIds.has(id)))
  };
}

function buildGraphIndexes(trace: PlanTrace) {
  const nodeMap = new Map(trace.graph.nodes.map((node) => [node.id, node]));
  const outgoing = new Map<string, TraceEdge[]>();
  const incoming = new Map<string, TraceEdge[]>();

  for (const edge of trace.graph.edges) {
    const out = outgoing.get(edge.source) || [];
    out.push(edge);
    outgoing.set(edge.source, out);

    const inc = incoming.get(edge.target) || [];
    inc.push(edge);
    incoming.set(edge.target, inc);
  }

  return { nodeMap, outgoing, incoming };
}

function getBranchPlan(trace: PlanTrace, l1Id: string, hitOnly = false): BranchPlan {
  const { nodeMap, outgoing } = buildGraphIndexes(trace);
  const l2Edges = (outgoing.get(l1Id) || []).filter((edge) => nodeMap.get(edge.target)?.type === 'fault_l2');
  const l2NodeIds = l2Edges.map((edge) => edge.target);
  const l2Nodes = l2NodeIds
    .map((id) => nodeMap.get(id))
    .filter((node): node is TraceNode => Boolean(node))
    .filter((node) => !hitOnly || node.isHit || node.isFocus);

  const level1EdgeIds = hitOnly ? [] : [`root-to-${l1Id}`];
  const level1NodeIds = [l1Id];
  const level2EdgeIds = l2Edges
    .filter((edge) => l2Nodes.some((node) => node.id === edge.target))
    .map((edge) => edge.id);
  const level2NodeIds = l2Nodes.map((node) => node.id);

  const level3Edges: string[] = [];
  const level3Nodes: string[] = [];
  const level4Edges: string[] = [];
  const level4Nodes: string[] = [];

  for (const l2Node of l2Nodes) {
    const edges3 = outgoing.get(l2Node.id) || [];
    for (const edge3 of edges3) {
      const level3Node = nodeMap.get(edge3.target);
      if (!level3Node) continue;
      if (hitOnly && !(level3Node.isHit || level3Node.isFocus)) continue;
      level3Edges.push(edge3.id);
      level3Nodes.push(level3Node.id);

      const edges4 = outgoing.get(level3Node.id) || [];
      for (const edge4 of edges4) {
        const level4Node = nodeMap.get(edge4.target);
        if (!level4Node) continue;
        if (hitOnly && !(level4Node.isHit || level4Node.isFocus)) continue;
        level4Edges.push(edge4.id);
        level4Nodes.push(level4Node.id);
      }
    }
  }

  return {
    l1Id,
    edgeLevels: [
      level1EdgeIds.filter(Boolean),
      level2EdgeIds,
      [...new Set(level3Edges)],
      [...new Set(level4Edges)]
    ],
    nodeLevels: [
      level1NodeIds,
      level2NodeIds,
      [...new Set(level3Nodes)],
      [...new Set(level4Nodes)]
    ]
  };
}

function getRootEdgeId(trace: PlanTrace, l1Id: string) {
  const root = trace.graph.nodes.find((node) => node.type === 'root_node');
  const edge = trace.graph.edges.find((item) => item.source === root?.id && item.target === l1Id);
  return edge?.id || '';
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function buildTraceAnimationPlans(trace: PlanTrace) {
  const { nodeMap, outgoing } = buildGraphIndexes(trace);
  const root = trace.graph.nodes.find((node) => node.type === 'root_node');
  const l1Nodes = (root ? outgoing.get(root.id) || [] : [])
    .map((edge) => nodeMap.get(edge.target))
    .filter((node): node is TraceNode => Boolean(node && node.type === 'fault_l1'));

  const focusL1 = l1Nodes.find((node) => node.isHit) || l1Nodes[0];
  const focusIndex = l1Nodes.findIndex((node) => node.id === focusL1?.id);
  const focusHitPlan = focusL1 ? getBranchPlan(trace, focusL1.id, true) : null;
  if (focusHitPlan && focusL1) {
    focusHitPlan.edgeLevels[0] = [getRootEdgeId(trace, focusL1.id)].filter(Boolean);
  }

  const focusFullPlan = focusL1 ? getBranchPlan(trace, focusL1.id, false) : null;
  if (focusFullPlan && focusL1) {
    focusFullPlan.edgeLevels[0] = [getRootEdgeId(trace, focusL1.id)].filter(Boolean);
  }

  const focusNodeIds = new Set<string>((focusHitPlan?.nodeLevels || []).flat());
  const focusEdgeIds = new Set<string>((focusHitPlan?.edgeLevels || []).flat());
  const focusRemainderPlan = filterPlan(focusFullPlan, focusNodeIds, focusEdgeIds);

  const clockwisePlans: BranchPlan[] = [];
  if (focusIndex >= 0) {
    for (let offset = 1; offset < l1Nodes.length; offset += 1) {
      const nextIndex = (focusIndex + offset) % l1Nodes.length;
      const next = l1Nodes[nextIndex];
      if (!next) continue;
      const plan = getBranchPlan(trace, next.id, false);
      plan.edgeLevels[0] = [getRootEdgeId(trace, next.id)].filter(Boolean);
      clockwisePlans.push(plan);
    }
  }

  return { rootId: root?.id || '', focusHitPlan, focusRemainderPlan, clockwisePlans };
}

export function createTraceAnimationController(params: {
  trace: PlanTrace;
  graph: any;
  darkMode: boolean;
  width: number;
  height: number;
}) {
  const { trace, graph, darkMode, width, height } = params;
  const { rootId, focusHitPlan, focusRemainderPlan, clockwisePlans } = buildTraceAnimationPlans(trace);

  const visibleNodeIds = new Set<string>(rootId ? [rootId] : []);
  const visibleEdgeIds = new Set<string>();
  const ghostNodeIds = new Set<string>();
  let stopped = false;
  const timers: number[] = [];

  const flush = async () => {
    if (stopped) return;
    graph.setData(buildVisibleTraceGraphData(trace, darkMode, width, height, visibleNodeIds, visibleEdgeIds, ghostNodeIds));
    await graph.render();
  };

  const playBranch = async (plan: BranchPlan | null, onAfterLevel2?: () => void) => {
    if (!plan || stopped) return;
    for (let index = 0; index < plan.edgeLevels.length; index += 1) {
      for (const nodeId of plan.nodeLevels[index]) {
        if (!visibleNodeIds.has(nodeId)) {
          ghostNodeIds.add(nodeId);
        }
      }
      for (const edgeId of plan.edgeLevels[index]) visibleEdgeIds.add(edgeId);
      await flush();
      await delay(160);
      for (const nodeId of plan.nodeLevels[index]) {
        ghostNodeIds.delete(nodeId);
        visibleNodeIds.add(nodeId);
      }
      await flush();
      if (index === 1 && onAfterLevel2) {
        onAfterLevel2();
      }
      await delay(140);
    }
  };

  const startClockwiseSequence = (plans: BranchPlan[], startIndex: number) => {
    const plan = plans[startIndex];
    if (!plan || stopped) return;
    let nextScheduled = false;
    void playBranch(plan, () => {
      if (nextScheduled) return;
      nextScheduled = true;
      const nextPlan = plans[startIndex + 1];
      if (!nextPlan || stopped) return;
      const timer = window.setTimeout(() => {
        startClockwiseSequence(plans, startIndex + 1);
      }, 200);
      timers.push(timer);
    });
  };

  const start = async () => {
    await flush();
    await delay(120);
    await playBranch(focusHitPlan);
    await playBranch(focusRemainderPlan);
    if (clockwisePlans.length) {
      startClockwiseSequence(clockwisePlans, 0);
    }
  };

  const stop = () => {
    stopped = true;
    timers.forEach((id) => window.clearTimeout(id));
  };

  return { start, stop };
}
