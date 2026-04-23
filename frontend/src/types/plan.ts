export type PipelineStage =
  | 'idle'
  | 'basic_info'
  | 'template_split'
  | 'parallel_generating'
  | 'case_search'
  | 'done'
  | 'error';

export interface PipelineRunRequest {
  question: string;
  enableCaseSearch?: boolean;
  enableMultiFaultSearch?: boolean;
}

export interface PipelineBasicInfo {
  userQuestion: string;
  faultScene: string;
  graphMaterial: string;
}

export interface PipelineTemplateSplit {
  templateId: string;
  templateName: string;
  currentVersion: string;
  chapterCount: number;
}

export interface PipelineChapter {
  chapterNo: string;
  title: string;
  sectionCount: number;
  templateText: string;
  outputText: string;
  elapsedSec?: number;
  status: 'pending' | 'running' | 'done' | 'error';
}

export interface PipelineRunResponse {
  question: string;
  basicInfo: PipelineBasicInfo;
  templateSplit: PipelineTemplateSplit;
  chapters: PipelineChapter[];
  caseSearch?: PipelineCaseSearchResult;
  raw?: unknown;
}

export interface PipelineCaseSearchResult {
  enabled: boolean;
  status: 'idle' | 'running' | 'done' | 'skipped' | 'error';
  kbName?: string;
  datasetId?: string;
  queryQuestion?: string;
  outputText?: string;
  cards?: PipelineCaseSearchCard[];
  error?: string;
}

export interface PipelineCaseSearchCard {
  id?: string;
  title: string;
  kbId: string;
  docId: string;
  relevance: string;
  excerpt: string;
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
  isFocus?: boolean;
  isHit?: boolean;
}

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  isHit?: boolean;
}
