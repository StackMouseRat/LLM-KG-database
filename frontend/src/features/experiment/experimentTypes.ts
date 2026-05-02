import type { ExperimentQuestionItem } from './experimentApi';

export type ExperimentStepStatus = 'pending' | 'running' | 'done' | 'failed';
export type ExperimentCardView = 'info' | 'control' | 'preview' | 'evaluation';
export type ExperimentControlStage = 'generation' | 'evaluation';

export type ExperimentStageState = {
  status: 'idle' | 'running' | 'done' | 'error' | 'interrupted';
  progress: number;
  message?: string;
};

export type ExperimentControlState = {
  runCount: number;
  concurrency: number;
  evaluationConcurrency: number;
  generation: ExperimentStageState;
  evaluation: ExperimentStageState;
};

export type ExperimentGroupOutput = {
  groupId: string;
  groupLabel: string;
  question: string;
  questionItem?: ExperimentQuestionItem;
  outputText: string;
  streamingText: string;
  status: 'running' | 'done' | 'terminated' | 'error';
};

export type ExperimentActiveGroup = {
  key: string;
  round: number;
  groupId: string;
  groupLabel: string;
};

export type ExperimentOutputState = {
  current?: {
    round: number;
    groupId: string;
    groupLabel: string;
  };
  activeGroups?: ExperimentActiveGroup[];
  activeRound?: number;
  roundQuestions: Record<string, string>;
  roundQuestionItems?: Record<string, ExperimentQuestionItem>;
  rounds: Record<string, Record<string, ExperimentGroupOutput>>;
};

export type ExperimentEvaluationScore = {
  groupId: string;
  groupLabel: string;
  score?: number;
  structuredEvaluation?: Record<string, any>;
  structuredError?: string;
  status: 'pending' | 'running' | 'done' | 'error';
  comment?: string;
};

export type ExperimentEvaluationState = {
  status: 'idle' | 'running' | 'done' | 'error';
  progress: number;
  current?: {
    round: number;
    groupId: string;
    groupLabel: string;
  };
  scores: Record<string, Record<string, ExperimentEvaluationScore>>;
  balanceSnapshots?: Array<Record<string, any>>;
  message?: string;
};

export type ExperimentGroupProgress = {
  activeStepIndex?: number;
  completedStepIndexes?: number[];
  failedStepIndex?: number;
};

export type ExperimentPlanProgress = Partial<Record<string, ExperimentGroupProgress>>;
export type ExperimentProgressByPlan = Partial<Record<string, ExperimentPlanProgress>>;

export type ExperimentFlowNode = {
  plugin: string;
  input: string;
  output: string;
  mode?: '主链路' | '并发分支' | '逐章并发' | '逐故障并发';
  variables?: string[];
  connectsToNext?: boolean;
};

export type SupportLayerTag = '图谱' | '模板' | '案例' | '工作流';

export type ExperimentProcessGroup = {
  id: string;
  role: '对照组' | '实验组';
  name: string;
  summary: string;
  supportTags?: SupportLayerTag[];
  nodes: ExperimentFlowNode[];
};

export type ExperimentPlan = {
  id: string;
  title: string;
  tag: string;
  objective: string;
  processGroups: ExperimentProcessGroup[];
  inputs: string[];
  questionSuiteId?: string;
  expectedInput: string;
  expectedOutput: string[];
  metrics: string[];
};

export type ExperimentEvaluationTask = {
  round: number;
  group: ExperimentProcessGroup;
  output: ExperimentGroupOutput;
};

export type ExperimentPageSnapshot = {
  cardViewMap?: Record<string, ExperimentCardView>;
  controlStateMap?: Record<string, ExperimentControlState>;
  outputStateMap?: Record<string, ExperimentOutputState>;
  evaluationStateMap?: Record<string, ExperimentEvaluationState>;
  sampledQuestionMap?: Record<string, ExperimentQuestionItem[]>;
  selectedRunIdMap?: Record<string, string>;
  evaluationCompactModeMap?: Record<string, boolean>;
};

export const defaultStageState: ExperimentStageState = {
  status: 'idle',
  progress: 0
};

export const defaultControlState: ExperimentControlState = {
  runCount: 4,
  concurrency: 2,
  evaluationConcurrency: 2,
  generation: defaultStageState,
  evaluation: defaultStageState
};

export const defaultOutputState: ExperimentOutputState = {
  activeGroups: [],
  roundQuestions: {},
  roundQuestionItems: {},
  rounds: {}
};

export const defaultEvaluationState: ExperimentEvaluationState = {
  status: 'idle',
  progress: 0,
  scores: {}
};

export const experimentStepStatusText: Record<ExperimentStepStatus, string> = {
  pending: '待运行',
  running: '进行中',
  done: '已完成',
  failed: '异常'
};
