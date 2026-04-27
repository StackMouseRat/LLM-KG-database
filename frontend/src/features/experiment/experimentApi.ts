export type ExperimentSuiteQuestion = {
  questionId: string;
  groupId: string;
  groupCode: string;
  questionText: string;
  expectedBehavior: string;
  category: string;
  sortOrder: number;
  enabled: boolean;
};

export type ExperimentSuiteGroup = {
  groupId: string;
  code: string;
  name: string;
  purpose: string;
  expectedBehavior: string;
  sortOrder: number;
  questions: ExperimentSuiteQuestion[];
};

export type ExperimentQuestionSuite = {
  suiteId: string;
  name: string;
  description: string;
  experimentId: string;
  version: string;
  questionCount: number;
  createdAt: string;
  evaluationPrompt: string;
  groups: ExperimentSuiteGroup[];
};

export type ExperimentRunSummary = {
  runId: string;
  name: string;
  planId: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  runCount: number;
  concurrency: number;
  completedGroups: number;
  totalGroups: number;
  questions: string[];
  questionItems?: ExperimentQuestionItem[];
  evaluationStatus?: string;
  evaluatedGroups?: number;
  totalEvaluations?: number;
  evaluationUpdatedAt?: string;
};

export type ExperimentQuestionItem = {
  questionId?: string;
  questionText: string;
  groupId?: string;
  groupCode?: string;
  groupName?: string;
  expectedBehavior?: string;
  category?: string;
};

export type ExperimentRunDetail = {
  run: ExperimentRunSummary;
  outputState: {
    roundQuestions: Record<string, string>;
    roundQuestionItems?: Record<string, ExperimentQuestionItem>;
    rounds: Record<string, Record<string, any>>;
  };
  evaluationState?: Record<string, any>;
  evaluationRecord?: Record<string, any>;
  manifest: Record<string, any>;
};

async function readJsonSafely(response: Response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`响应不是有效 JSON：${text.slice(0, 160)}`);
  }
}

export async function fetchExperimentQuestionSuite(suiteId: string): Promise<ExperimentQuestionSuite> {
  const response = await fetch(`/api/evaluation/question-suite?suiteId=${encodeURIComponent(suiteId)}`, {
    credentials: 'include'
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.suite as ExperimentQuestionSuite;
}

export async function fetchExperimentRuns(planId: string): Promise<ExperimentRunSummary[]> {
  const response = await fetch(`/api/experiment/runs?planId=${encodeURIComponent(planId)}`, {
    credentials: 'include'
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return (data?.runs || []) as ExperimentRunSummary[];
}

export async function fetchExperimentRunDetail(planId: string, runId: string): Promise<ExperimentRunDetail> {
  const response = await fetch(`/api/experiment/run?planId=${encodeURIComponent(planId)}&runId=${encodeURIComponent(runId)}`, {
    credentials: 'include'
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data as ExperimentRunDetail;
}

export async function saveExperimentEvaluation(planId: string, runId: string, evaluationState: Record<string, any>) {
  const response = await fetch('/api/experiment/evaluation', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ planId, runId, evaluationState })
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data;
}
