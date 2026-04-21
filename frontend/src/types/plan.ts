export type GenerateStage =
  | 'idle'
  | 'detecting_device'
  | 'querying_graph'
  | 'generating'
  | 'done'
  | 'error';

export interface GeneratePlanRequest {
  question: string;
  stream?: boolean;
}

export interface GeneratePlanResponse {
  answer: string;
  trace: PlanTrace;
  raw?: unknown;
}

export interface StreamEventPayload {
  event?: string;
  data?: any;
}

export interface PlanTrace {
  device?: string;
  fault?: string;
  graph: TraceGraph;
  rawDetail?: unknown;
}

export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceEdge[];
}

export interface TraceNode {
  id: string;
  label: string;
  type:
    | 'root_node'
    | 'fault_l1'
    | 'fault_l2'
    | 'fault_cause'
    | 'fault_symptom'
    | 'response_measure'
    | 'fault_consequence'
    | 'safety_risk'
    | 'emergency_resource'
    | 'unknown';
  desc?: string;
  source?: 'KG' | 'GEN';
}

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}
