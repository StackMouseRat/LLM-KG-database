import type { PlanTrace, TraceNode } from '../types/plan';

function inferNodeType(name: string): TraceNode['type'] {
  if (name.endsWith('-故障原因')) return 'fault_cause';
  if (name.endsWith('-故障现象')) return 'fault_symptom';
  if (name.endsWith('-应对措施')) return 'response_measure';
  if (name.endsWith('-故障后果')) return 'fault_consequence';
  if (name.endsWith('-安全风险')) return 'safety_risk';
  if (name.endsWith('-应急资源')) return 'emergency_resource';
  return 'fault_l2';
}

function stripQuotes(value: string) {
  return value.trim().replace(/^"(.*)"$/, '$1');
}

function parseNebulaRows(stdout: string) {
  const tableLines = stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith('|') && line.endsWith('|') && !line.includes('+--'));

  if (tableLines.length < 2) return [];
  const header = tableLines[0].split('|').slice(1, -1).map(stripQuotes);
  return tableLines.slice(1).map((line) => {
    const cells = line.split('|').slice(1, -1).map(stripQuotes);
    return Object.fromEntries(header.map((key, index) => [key, cells[index] ?? '']));
  });
}

export function parseTraceFromFastGPT(data: any): PlanTrace {
  const modules = Array.isArray(data?.responseData) ? data.responseData : [];
  const deviceModule = modules.find((item: any) => item.moduleName === '设备识别');
  const faultModule = modules.find((item: any) => item.moduleName === '故障类型分析');
  const graphModule = modules.find((item: any) => item.moduleName === '下游节点获取');

  const device = deviceModule?.extractResult?.设备表;
  const fault = faultModule?.extractResult?.故障二级节点;
  const stdout = graphModule?.httpResult?.stdout ?? '';
  const rows = parseNebulaRows(stdout);

  const nodes: TraceNode[] = rows
    .filter((row) => row.name)
    .map((row, index) => ({
      id: `${index}`,
      label: row.name,
      type: inferNodeType(row.name),
      desc: row.node_desc,
      source: 'KG'
    }));

  return {
    device,
    fault,
    graph: {
      nodes,
      edges: []
    },
    rawDetail: data
  };
}
