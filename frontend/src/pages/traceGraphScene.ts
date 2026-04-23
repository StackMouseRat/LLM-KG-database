import type { PlanTrace, TraceNode } from '../types/plan';

export const NODE_COLOR_MAP: Record<TraceNode['type'], string> = {
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

export const LEVEL3_RADIAL_OFFSET_STEP = 30;
export const LEVEL4_RADIAL_OFFSET_STEP = 50;

export function getNodeSize(node: TraceNode): [number, number] {
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

export function polarToCartesian(cx: number, cy: number, radius: number, angle: number) {
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle)
  };
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

function getEdgeDisplayLabel(label: string) {
  const mapping: Record<string, string> = {
    发生: '发生',
    包含: '包含',
    故障原因: '原因',
    故障现象: '现象',
    故障后果: '后果',
    应对措施: '应对',
    安全风险: '风险',
    应急资源: '资源'
  };
  return mapping[String(label || '')] || String(label || '').slice(0, 2);
}

export function computeTraceLayout(trace: PlanTrace, width: number, height: number) {
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
  const l1Radius = 180;
  const l2Radius = 540;
  const l3Radius = 680;
  const l4Radius = 900;

  level1.forEach((node, index) => {
    const angle = -Math.PI / 2 + ((index + 0.5) * fullCircle) / Math.max(1, level1.length);
    positions[node.id] = polarToCartesian(centerX, centerY, l1Radius, angle);
    visibleNodeIds.add(node.id);
  });

  level2.forEach((node, index) => {
    const angle = -Math.PI / 2 + ((index + 0.5) * fullCircle) / Math.max(1, level2.length);
    positions[node.id] = polarToCartesian(centerX, centerY, l2Radius, angle);
    visibleNodeIds.add(node.id);
  });

  for (const l1Node of level1) {
    const l2Children = (outgoing.get(l1Node.id) || [])
      .map((id) => nodeMap.get(id))
      .filter((node): node is TraceNode => Boolean(node && node.type === 'fault_l2'));

    const level3Branch = level3
      .filter((node) => {
        const parentL2 = [...outgoing.entries()].find(([, targets]) => targets.includes(node.id))?.[0] || '';
        return l2Children.some((child) => child.id === parentL2);
      })
      .sort((a, b) => {
        const aParent = [...outgoing.entries()].find(([, targets]) => targets.includes(a.id))?.[0] || '';
        const bParent = [...outgoing.entries()].find(([, targets]) => targets.includes(b.id))?.[0] || '';
        const aIndex = level2.findIndex((node) => node.id === aParent);
        const bIndex = level2.findIndex((node) => node.id === bParent);
        return aIndex - bIndex;
      });

    level3Branch.forEach((node, index) => {
      const globalIndex = level3.findIndex((item) => item.id === node.id);
      const angle = -Math.PI / 2 + ((globalIndex + 0.5) * fullCircle) / Math.max(1, level3.length);
      const layerIndex = index === 0 ? 0 : Math.min(index, level3Branch.length - index);
      const layerOffset = layerIndex * LEVEL3_RADIAL_OFFSET_STEP;
      positions[node.id] = polarToCartesian(centerX, centerY, l3Radius + layerOffset, angle);
      visibleNodeIds.add(node.id);
    });

    const level4Branch = level4
      .filter((node) => {
        const parentL3 = [...outgoing.entries()].find(([, targets]) => targets.includes(node.id))?.[0] || '';
        const parentL2 = [...outgoing.entries()].find(([, targets]) => targets.includes(parentL3))?.[0] || '';
        return l2Children.some((child) => child.id === parentL2);
      })
      .sort((a, b) => {
        const aL3 = [...outgoing.entries()].find(([, targets]) => targets.includes(a.id))?.[0] || '';
        const bL3 = [...outgoing.entries()].find(([, targets]) => targets.includes(b.id))?.[0] || '';
        const aL2 = [...outgoing.entries()].find(([, targets]) => targets.includes(aL3))?.[0] || '';
        const bL2 = [...outgoing.entries()].find(([, targets]) => targets.includes(bL3))?.[0] || '';
        const aIndex = level2.findIndex((node) => node.id === aL2);
        const bIndex = level2.findIndex((node) => node.id === bL2);
        return aIndex - bIndex;
      });

    level4Branch.forEach((node, index) => {
      const globalIndex = level4.findIndex((item) => item.id === node.id);
      const angle = -Math.PI / 2 + ((globalIndex + 0.5) * fullCircle) / Math.max(1, level4.length);
      const layerIndex = index === 0 ? 0 : Math.min(index, level4Branch.length - index);
      const layerOffset = layerIndex * LEVEL4_RADIAL_OFFSET_STEP;
      positions[node.id] = polarToCartesian(centerX, centerY, l4Radius + layerOffset, angle);
      visibleNodeIds.add(node.id);
    });
  }

  return { positions, visibleNodeIds };
}

export function buildTraceGraphData(trace: PlanTrace, darkMode: boolean, width: number, height: number) {
  const layoutResult = computeTraceLayout(trace, width, height);
  const nodePositions = layoutResult.positions;
  const visibleNodeIds = layoutResult.visibleNodeIds;

  return {
    visibleNodeIds,
    graphData: {
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
            label: getEdgeDisplayLabel(edge.label),
            isHit: Boolean(edge.isHit),
            stroke: edge.isHit ? (darkMode ? '#94a3b8' : '#64748b') : darkMode ? '#334155' : '#cbd5e1'
          }
        }))
    }
  };
}
