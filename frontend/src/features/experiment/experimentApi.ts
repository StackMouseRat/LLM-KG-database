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

export async function fetchExperimentQuestionSuite(suiteId: string): Promise<ExperimentQuestionSuite> {
  const response = await fetch(`/api/evaluation/question-suite?suiteId=${encodeURIComponent(suiteId)}`, {
    credentials: 'include'
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.suite as ExperimentQuestionSuite;
}
