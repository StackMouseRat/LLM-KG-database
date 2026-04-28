import type { ExperimentQuestionItem, ExperimentQuestionSuite, ExperimentRunSummary } from './experimentApi';
import {
  defaultStageState,
  type ExperimentActiveGroup,
  type ExperimentControlState,
  type ExperimentEvaluationState,
  type ExperimentGroupOutput,
  type ExperimentOutputState,
  type ExperimentPageSnapshot,
  type ExperimentProcessGroup,
  type ExperimentStageState
} from './experimentTypes';

export function splitGroupName(group: ExperimentProcessGroup) {
  const [label, ...rest] = group.name.split('：');
  return {
    label: rest.length ? label : group.role,
    title: rest.length ? rest.join('：') : group.name
  };
}

export function getRuntimeChanges(group: ExperimentProcessGroup, node: { variables?: string[] }) {
  if (group.role === '对照组') return [];
  return node.variables && node.variables.length > 0
    ? node.variables
        .map((variable) => variable.replace('调用并行生成插件', ''))
        .filter((variable) => !variable.startsWith('无上游变量'))
    : [];
}

export function getSupportLayerTags(group: ExperimentProcessGroup) {
  return group.supportTags || ['图谱', '模板', '工作流'];
}

export function getActiveControlStage(state: ExperimentControlState) {
  return state.generation.status === 'running' ? state.generation : state.evaluation.status === 'running' ? state.evaluation : state.generation.status === 'done' ? state.generation : state.evaluation;
}

export function getStageStatusText(status: ExperimentStageState['status']) {
  if (status === 'running') return '运行中';
  if (status === 'done') return '已完成';
  if (status === 'error') return '异常';
  return '待启动';
}

export function getProgressStatus(status: ExperimentStageState['status']) {
  if (status === 'error') return 'exception';
  if (status === 'done') return 'success';
  if (status === 'running') return 'active';
  return 'normal';
}

export function getSuiteQuestionItems(suite: ExperimentQuestionSuite | undefined): ExperimentQuestionItem[] {
  if (!suite) return [];
  return suite.groups.flatMap((group) => group.questions.map((question) => ({
    ...question,
    groupId: question.groupId || group.groupId,
    groupCode: question.groupCode || group.code,
    groupName: group.name,
    category: question.category,
    expectedBehavior: question.expectedBehavior || group.expectedBehavior
  })));
}

export function pickRandomQuestionItems(questions: ExperimentQuestionItem[], count: number) {
  return [...questions]
    .sort(() => Math.random() - 0.5)
    .slice(0, count);
}

export function questionItemLabel(item?: ExperimentQuestionItem) {
  if (!item) return '';
  return [item.groupCode, item.groupName].filter(Boolean).join(' · ');
}

export function expectedBehaviorLabel(value?: string) {
  if (value === 'terminate') return '应终止';
  if (value === 'terminate_or_clarify') return '应终止或澄清';
  if (value === 'terminate_or_ignore_injection') return '应终止或忽略注入';
  if (value === 'generate') return '应放行生成';
  if (value === 'identify_fault_subject') return '应识别故障主体';
  if (value === 'identify_primary_subject') return '应识别主故障主体';
  if (value === 'identify_primary_and_affected_subjects') return '应识别主故障及受影响主体';
  return value || '未提供';
}

export function eventQuestionItem(data: any): ExperimentQuestionItem | undefined {
  return data?.questionItem && typeof data.questionItem === 'object' && String(data.questionItem.questionText || '').trim()
    ? data.questionItem as ExperimentQuestionItem
    : undefined;
}

export function mergeRoundQuestionItem(current: ExperimentOutputState, roundKey: string, item?: ExperimentQuestionItem) {
  if (!item) return current.roundQuestionItems;
  return { ...(current.roundQuestionItems || {}), [roundKey]: item };
}

export function getMaxExperimentConcurrency(runCount: number, groupCount: number) {
  return Math.max(1, Math.min(runCount * groupCount, 15));
}

export function getMaxEvaluationConcurrency() {
  return 10;
}

export function sanitizeStageState(state?: ExperimentStageState): ExperimentStageState {
  if (!state) return defaultStageState;
  return state.status === 'running'
    ? { ...state, status: 'idle', message: undefined }
    : state;
}

export function sanitizeControlStateMap(map: Record<string, ExperimentControlState>) {
  return Object.fromEntries(Object.entries(map).map(([planId, state]) => [
    planId,
    {
      ...state,
      generation: sanitizeStageState(state.generation),
      evaluation: sanitizeStageState(state.evaluation)
    }
  ]));
}

export function sanitizeEvaluationStateMap(map: Record<string, ExperimentEvaluationState>) {
  return Object.fromEntries(Object.entries(map).map(([planId, state]) => [
    planId,
    {
      ...state,
      status: state.status === 'running' ? 'idle' : state.status,
      current: undefined,
      scores: Object.fromEntries(Object.entries(state.scores || {}).map(([round, groupMap]) => [
        round,
        Object.fromEntries(Object.entries(groupMap || {}).map(([groupId, score]) => [
          groupId,
          score.status === 'running' ? { ...score, status: 'pending' as const } : score
        ]))
      ]))
    }
  ]));
}

export function buildExperimentPageSnapshot(snapshot: ExperimentPageSnapshot): ExperimentPageSnapshot {
  return {
    cardViewMap: snapshot.cardViewMap || {},
    controlStateMap: sanitizeControlStateMap(snapshot.controlStateMap || {}),
    outputStateMap: snapshot.outputStateMap || {},
    evaluationStateMap: sanitizeEvaluationStateMap(snapshot.evaluationStateMap || {}),
    sampledQuestionMap: snapshot.sampledQuestionMap || {},
    selectedRunIdMap: snapshot.selectedRunIdMap || {},
    evaluationCompactModeMap: snapshot.evaluationCompactModeMap || {}
  };
}

export function activeGroupKey(round: number, groupId: string) {
  return `${round}:${groupId}`;
}

export function addActiveGroup(current: ExperimentOutputState, group: Omit<ExperimentActiveGroup, 'key'>) {
  const key = activeGroupKey(group.round, group.groupId);
  const activeGroups = (current.activeGroups || []).filter((item) => item.key !== key);
  return [...activeGroups, { ...group, key }].sort((a, b) => a.round - b.round || a.groupLabel.localeCompare(b.groupLabel));
}

export function removeActiveGroup(current: ExperimentOutputState, round: number, groupId: string) {
  const key = activeGroupKey(round, groupId);
  return (current.activeGroups || []).filter((item) => item.key !== key);
}

export function formatStructuredEvaluation(value?: Record<string, any>) {
  if (!value) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function getVerdictColor(verdict?: string) {
  if (verdict === 'pass') return 'green';
  if (verdict === 'partial') return 'gold';
  if (verdict === 'fail') return 'red';
  return 'default';
}

export function getVerdictText(verdict?: string) {
  if (verdict === 'pass') return '通过';
  if (verdict === 'partial') return '部分通过';
  if (verdict === 'fail') return '不通过';
  return '未知';
}

export function getScoreTagColor(score?: number) {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'default';
  if (score > 8.9) return 'green';
  if (score > 7.5) return 'gold';
  return 'red';
}

export function formatScore(score?: number | string) {
  const value = Number(score);
  if (!Number.isFinite(value)) return '-';
  return value.toFixed(1);
}

export function formatScoreText(score?: number | string, maxScore: number | string = 10) {
  return `${formatScore(score)}/${formatScore(maxScore)}`;
}

export function getStructuredSubscores(value?: Record<string, any>) {
  const subscores = value?.subscores;
  return Array.isArray(subscores) ? subscores.filter((item) => item && typeof item === 'object') : [];
}

export function hasInlineSubscores(text: string) {
  return /(?:^|\n)\s*(?:\*\*)?[^\n：:]{2,40}(?:\*\*)?\s*[：:]?\s*\d+(?:\.\d+)?\s*\/\s*\d+(?:\.\d+)?/.test(text);
}

export function isValidStructuredEvaluation(value?: Record<string, any>, sourceText = '') {
  if (!value || !Object.keys(value).length) return false;
  const score = Number(value.score);
  if (!Number.isFinite(score) && !value.score_text) return false;
  if (hasInlineSubscores(sourceText) && !getStructuredSubscores(value).length) return false;
  return true;
}

const beijingTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false
});

function dateFromRunId(runId?: string) {
  const match = String(runId || '').match(/_(\d{12,})_/);
  if (!match) return undefined;
  const timestamp = Number(match[1]);
  if (!Number.isFinite(timestamp)) return undefined;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

export function formatBeijingTime(value?: string, fallbackRunId?: string) {
  const date = value ? new Date(value) : dateFromRunId(fallbackRunId);
  const safeDate = date && !Number.isNaN(date.getTime()) ? date : dateFromRunId(fallbackRunId);
  if (!safeDate || Number.isNaN(safeDate.getTime())) return value || fallbackRunId || '';
  const parts = Object.fromEntries(beijingTimeFormatter.formatToParts(safeDate).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} 北京时间`;
}

export function runRecordLabel(run: ExperimentRunSummary) {
  const generation = `${run.completedGroups}/${run.totalGroups}`;
  const evaluation = run.totalEvaluations ? ` · 评估 ${run.evaluatedGroups || 0}/${run.totalEvaluations}` : '';
  return `${run.name || `总次数${run.runCount} · 并发${run.concurrency}`} · 生成 ${generation}${evaluation} · ${formatBeijingTime(run.updatedAt, run.runId)}`;
}

export function evaluationRecordLabel(run: ExperimentRunSummary) {
  const evaluation = run.totalEvaluations ? `${run.evaluatedGroups || 0}/${run.totalEvaluations}` : '0/0';
  return `${run.name || `总次数${run.runCount} · 并发${run.concurrency}`} · 评估 ${evaluation} · ${formatBeijingTime(run.evaluationUpdatedAt || run.updatedAt, run.runId)}`;
}

export function hasEvaluationRecord(run?: ExperimentRunSummary) {
  return Boolean(run?.evaluationUpdatedAt || run?.totalEvaluations || run?.evaluationStatus && run.evaluationStatus !== 'idle');
}

export function getAverageScore(evaluationState: ExperimentEvaluationState) {
  const values = Object.values(evaluationState.scores)
    .flatMap((groupMap) => Object.values(groupMap))
    .map((item) => item.score)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
  if (!values.length) return undefined;
  return Math.round((values.reduce((sum, score) => sum + score, 0) / values.length) * 10) / 10;
}

export function getGroupAverageScores(plan: { processGroups: ExperimentProcessGroup[] }, evaluationState: ExperimentEvaluationState) {
  return plan.processGroups.map((group) => {
    const values = Object.values(evaluationState.scores)
      .map((groupMap) => groupMap[group.id]?.score)
      .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
    return {
      group,
      average: values.length ? Math.round((values.reduce((sum, score) => sum + score, 0) / values.length) * 10) / 10 : undefined
    };
  });
}

export function parseEvaluationScore(text: string) {
  const scoreMatch = text.match(/(\d+(?:\.\d+)?)\s*\/\s*10/) || text.match(/(?:总分|得分|评分|score)\D{0,12}(\d+(?:\.\d+)?)/i);
  if (!scoreMatch) return undefined;
  const score = Number(scoreMatch[1]);
  if (!Number.isFinite(score)) return undefined;
  return Math.max(0, Math.min(10, score));
}

export function buildGroupProgress(group: ExperimentProcessGroup, state: ExperimentControlState) {
  const stage = getActiveControlStage(state);
  const stepCount = Math.max(group.nodes.length, 1);
  const runCount = Math.max(state.runCount, 1);
  const totalUnits = runCount * stepCount;
  const completedUnits = Math.floor((stage.progress / 100) * totalUnits);
  const currentRun = stage.progress <= 0 ? 0 : Math.min(runCount, Math.max(1, Math.ceil((stage.progress / 100) * runCount)));

  if (stage.status === 'idle' || stage.status === 'error') {
    return {
      runLabel: `次数 0/${runCount}`,
      progress: { completedStepIndexes: [] }
    };
  }

  if (completedUnits >= totalUnits) {
    return {
      runLabel: `次数 ${runCount}/${runCount}`,
      progress: { completedStepIndexes: group.nodes.map((_, index) => index) }
    };
  }

  const activeStepIndex = completedUnits % stepCount;
  return {
    runLabel: `次数 ${currentRun}/${runCount}`,
    progress: {
      activeStepIndex,
      completedStepIndexes: group.nodes.map((_, index) => index).filter((index) => index < activeStepIndex)
    }
  };
}
