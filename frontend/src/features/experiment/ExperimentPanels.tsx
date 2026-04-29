import { Button, Collapse, InputNumber, Progress, Select, Space, Tag, Typography } from 'antd';
import { useState, type ReactNode } from 'react';
import type { ExperimentRunSummary } from './experimentApi';
import {
  experimentStepStatusText,
  type ExperimentControlStage,
  type ExperimentControlState,
  type ExperimentEvaluationState,
  type ExperimentGroupProgress,
  type ExperimentOutputState,
  type ExperimentPlan,
  type ExperimentPlanProgress,
  type ExperimentProcessGroup,
  type ExperimentStepStatus
} from './experimentTypes';
import {
  buildGroupProgress,
  evaluationRecordLabel,
  expectedBehaviorLabel,
  formatScore,
  formatScoreText,
  formatStructuredEvaluation,
  getActiveControlStage,
  getEvaluationDisplayScore,
  getGroupAverageScores,
  getMaxEvaluationConcurrency,
  getMaxExperimentConcurrency,
  getProgressStatus,
  getRuntimeChanges,
  getScoreTagColor,
  getStageStatusText,
  getStructuredSubscores,
  getSupportLayerTags,
  getVerdictColor,
  getVerdictText,
  hasEvaluationRecord,
  questionItemLabel,
  runRecordLabel,
  splitGroupName
} from './experimentUtils';

const { Paragraph, Text } = Typography;

const experimentProgressByPlan: Partial<Record<string, ExperimentPlanProgress>> = {};

function getExperimentStepStatus(progress: ExperimentPlanProgress | undefined, groupId: string, stepIndex: number): ExperimentStepStatus {
  const groupProgress = progress?.[groupId];
  if (groupProgress?.failedStepIndex === stepIndex) return 'failed';
  if (groupProgress?.activeStepIndex === stepIndex) return 'running';
  if (groupProgress?.completedStepIndexes?.includes(stepIndex)) return 'done';
  return 'pending';
}

export function ExperimentSection({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`experiment-plan-card__section${wide ? ' is-wide' : ''}`}>
      <Text strong>{title}</Text>
      {children}
    </div>
  );
}

export function ExperimentFlowDiagram({ planId, group, progress, showStatus = true }: { planId: string; group: ExperimentProcessGroup; progress?: ExperimentGroupProgress; showStatus?: boolean }) {
  const supportLayerTags = getSupportLayerTags(group);

  return (
    <div className="experiment-plan-card__flow-text">
      <ol className="experiment-plan-card__step-list">
        <li className="experiment-plan-card__step-frame">
          <div className="experiment-plan-card__runtime-strip is-support-data">
            <span>支撑层数据</span>
            <div className="experiment-plan-card__runtime-changes">
              {supportLayerTags.length > 0 ? (
                supportLayerTags.map((item) => (
                  <Tag color="green" key={item}>{item}</Tag>
                ))
              ) : (
                <Tag color="red">无</Tag>
              )}
            </div>
          </div>
        </li>
        {group.nodes.map((flowNode, index) => {
          const stepStatus = progress
            ? getExperimentStepStatus({ [group.id]: progress }, group.id, index)
            : getExperimentStepStatus(experimentProgressByPlan[planId], group.id, index);
          const runtimeChanges = getRuntimeChanges(group, flowNode);
          return (
            <li className="experiment-plan-card__step-frame" key={`${flowNode.plugin}-${index}`}>
              <div className="experiment-plan-card__step-item">
                <div className="experiment-plan-card__step-header">
                  <div className="experiment-plan-card__step-title-row">
                    <Text strong>{index + 1}. {flowNode.plugin}</Text>
                    <div className="experiment-plan-card__change-indicator">
                      {runtimeChanges.length === 0 ? (
                        <Tag color="green">无更改</Tag>
                      ) : (
                        runtimeChanges.map((variable) => (
                          <Tag color="red" key={variable}>{variable}</Tag>
                        ))
                      )}
                    </div>
                  </div>
                  <Space size={6} wrap>
                    {flowNode.mode && flowNode.mode !== '主链路' ? <Tag color="gold">{flowNode.mode}</Tag> : null}
                    {showStatus ? (
                      <Tag color={stepStatus === 'done' ? 'green' : stepStatus === 'failed' ? 'red' : stepStatus === 'running' ? 'blue' : 'default'}>
                        {experimentStepStatusText[stepStatus]}
                      </Tag>
                    ) : null}
                  </Space>
                </div>
                <div className="experiment-plan-card__step-body">
                  <div><Text type="secondary">输入：</Text>{flowNode.input}</div>
                  <div><Text type="secondary">输出：</Text>{flowNode.output}</div>
                </div>
              </div>
              {index < group.nodes.length - 1 ? (
                <div className="experiment-plan-card__runtime-strip">
                  <span>运行时控制</span>
                  <div className="experiment-plan-card__runtime-changes">
                    {runtimeChanges.length === 0 ? (
                      <Tag color="green">无变化</Tag>
                    ) : (
                      runtimeChanges.map((variable) => (
                        <Tag color="red" key={variable}>{variable}</Tag>
                      ))
                    )}
                  </div>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function ExperimentControlPanel({
  plan,
  state,
  evaluationState,
  runs,
  selectedRunId,
  outputState,
  onUpdateConfig,
  onRunStage,
  onSelectRun,
  onLoadRun,
  onRefreshRuns
}: {
  plan: ExperimentPlan;
  state: ExperimentControlState;
  evaluationState: ExperimentEvaluationState;
  runs: ExperimentRunSummary[];
  selectedRunId?: string;
  outputState: ExperimentOutputState;
  onUpdateConfig: (patch: Partial<Pick<ExperimentControlState, 'runCount' | 'concurrency' | 'evaluationConcurrency'>>) => void;
  onRunStage: (stage: ExperimentControlStage, options?: { runId?: string }) => void;
  onSelectRun: (runId: string) => void;
  onLoadRun: () => void;
  onRefreshRuns: () => void;
}) {
  const totalScripts = Math.max(plan.processGroups.length - 1, 0);
  const effectiveEvaluationStage = evaluationState.status !== 'idle' || evaluationState.progress > 0
    ? { status: evaluationState.status, progress: evaluationState.progress, message: evaluationState.message }
    : state.evaluation;
  const generationRunning = state.generation.status === 'running';
  const evaluationRunning = effectiveEvaluationStage.status === 'running';
  const maxConcurrency = getMaxExperimentConcurrency(state.runCount, plan.processGroups.length);
  const activeGroups = outputState.activeGroups || [];

  return (
    <div className="experiment-control-console">
      <div className="experiment-control-console__header">
        <div>
          <Text strong>实验控制台</Text>
          <Paragraph className="experiment-control-console__desc">
            每次生成都会保存服务端记录，可选择历史记录载入、继续生成或启动评估。
          </Paragraph>
        </div>
        <Space wrap>
          <Tag color="purple">{plan.title}</Tag>
          <Tag color="blue">实验脚本 {totalScripts} 个</Tag>
        </Space>
      </div>

      <div className="experiment-control-console__config">
        <label>
          <Text type="secondary">实验次数</Text>
          <InputNumber
            min={1}
            max={50}
            value={state.runCount}
            onChange={(value) => onUpdateConfig({ runCount: Math.max(Number(value || 1), 1) })}
          />
        </label>
        <label>
          <Text type="secondary">并发数</Text>
          <InputNumber
            min={1}
            max={maxConcurrency}
            value={state.concurrency}
            onChange={(value) => onUpdateConfig({ concurrency: Math.min(Number(value || 1), maxConcurrency) })}
          />
          <Text type="secondary">最多 {maxConcurrency} 个组</Text>
        </label>
        <label>
          <Text type="secondary">评估并发数</Text>
          <InputNumber
            min={1}
            max={getMaxEvaluationConcurrency()}
            value={state.evaluationConcurrency}
            onChange={(value) => onUpdateConfig({ evaluationConcurrency: Math.min(Number(value || 1), getMaxEvaluationConcurrency()) })}
          />
          <Text type="secondary">最多 {getMaxEvaluationConcurrency()} 个评分</Text>
        </label>
      </div>

      <div className="experiment-control-console__record-row">
        <Select
          allowClear
          placeholder="选择已保存实验结果"
          value={selectedRunId}
          onChange={(value) => onSelectRun(value || '')}
          options={runs.map((run) => ({
            value: run.runId,
            label: runRecordLabel(run)
          }))}
        />
        <Button size="small" onClick={onRefreshRuns}>刷新记录</Button>
        <Button size="small" disabled={!selectedRunId} onClick={onLoadRun}>载入结果</Button>
      </div>

      <div className="experiment-control-console__stages">
        <div className="experiment-control-console__stage">
          <div className="experiment-control-console__stage-header">
            <Text strong>阶段一：生成</Text>
            <Space size={8} wrap>
              <Button size="small" type="primary" loading={generationRunning} onClick={() => onRunStage('generation')}>
                新建生成
              </Button>
              <Button size="small" disabled={!selectedRunId} loading={generationRunning} onClick={() => onRunStage('generation', { runId: selectedRunId })}>
                继续生成
              </Button>
            </Space>
          </div>
          <Progress percent={state.generation.progress} size="small" status={getProgressStatus(state.generation.status)} />
          <Text type="secondary">按并发数运行实验脚本，生成各实验组预案正文。</Text>
          {state.generation.message ? <Text type="danger">{state.generation.message}</Text> : null}
        </div>

        <div className="experiment-control-console__stage">
          <div className="experiment-control-console__stage-header">
            <Text strong>阶段二：评估</Text>
            <Button size="small" disabled={!selectedRunId} loading={evaluationRunning} onClick={() => onRunStage('evaluation')}>
              启动评估
            </Button>
          </div>
          <Progress percent={effectiveEvaluationStage.progress} size="small" status={getProgressStatus(effectiveEvaluationStage.status)} />
          {evaluationState.current ? (
            <Text type="secondary">当前评估：第 {evaluationState.current.round} 轮 · {evaluationState.current.groupLabel}</Text>
          ) : (
            <Text type="secondary">先选择并载入某次实验结果，再对该结果进行自动评估。</Text>
          )}
          {effectiveEvaluationStage.message ? <Text type="danger">{effectiveEvaluationStage.message}</Text> : null}
        </div>
      </div>

      <div className="experiment-control-console__log">
        <Text type="secondary">实时进度</Text>
        <div>生成：{getStageStatusText(state.generation.status)} · {state.generation.progress}%</div>
        <div>评估：{getStageStatusText(effectiveEvaluationStage.status)} · {effectiveEvaluationStage.progress}%</div>
        <div className="experiment-control-console__active-groups">
          <Text type="secondary">当前并发：{activeGroups.length}/{state.concurrency}</Text>
          <div className="experiment-control-console__active-tags">
            {activeGroups.length ? activeGroups.map((group) => (
              <Tag color="blue" key={group.key}>第 {group.round} 轮 · {group.groupLabel}</Tag>
            )) : <Tag>暂无运行中组</Tag>}
          </div>
        </div>
      </div>

      <div className="experiment-control-console__groups">
        {plan.processGroups.map((group) => {
          const groupProgress = buildGroupProgress(group, state);
          return (
            <div className={`experiment-plan-card__group is-${group.role === '对照组' ? 'control' : 'experiment'}`} key={group.id}>
              <div className="experiment-plan-card__group-header">
                <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{splitGroupName(group).label}</Tag>
                <Text strong>{splitGroupName(group).title}</Text>
                <Tag color={getActiveControlStage(state).status === 'running' ? 'blue' : getActiveControlStage(state).status === 'done' ? 'green' : 'default'}>
                  {groupProgress.runLabel}
                </Tag>
              </div>
              <Paragraph className="experiment-plan-card__text">{group.summary}</Paragraph>
              <ExperimentFlowDiagram planId={plan.id} group={group} progress={groupProgress.progress} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ExperimentOutputPreview({
  plan,
  outputState,
  runs,
  selectedRunId,
  onSelectRun,
  onLoadRun,
  onRefreshRuns
}: {
  plan: ExperimentPlan;
  outputState: ExperimentOutputState;
  runs: ExperimentRunSummary[];
  selectedRunId?: string;
  onSelectRun: (runId: string) => void;
  onLoadRun: () => void;
  onRefreshRuns: () => void;
}) {
  const rounds = Object.entries(outputState.rounds).sort(([a], [b]) => Number(a) - Number(b));
  const activeGroups = outputState.activeGroups || [];

  return (
    <div className="experiment-output-preview">
      <div className="experiment-output-preview__header">
        <Text strong>产出预览</Text>
        {activeGroups.length ? (
          <div className="experiment-output-preview__active-groups">
            {activeGroups.map((group) => (
              <Tag color="blue" key={group.key}>运行中：第 {group.round} 轮 · {group.groupLabel}</Tag>
            ))}
          </div>
        ) : (
          <Tag>暂无运行中组</Tag>
        )}
      </div>
      <div className="experiment-control-console__record-row is-preview">
        <Select
          allowClear
          placeholder="选择已保存实验结果"
          value={selectedRunId}
          onChange={(value) => onSelectRun(value || '')}
          options={runs.map((run) => ({
            value: run.runId,
            label: runRecordLabel(run)
          }))}
        />
        <Button size="small" onClick={onRefreshRuns}>刷新记录</Button>
        <Button size="small" type="primary" disabled={!selectedRunId} onClick={onLoadRun}>载入结果</Button>
      </div>
      {rounds.length === 0 ? (
        <div className="experiment-output-preview__empty">启动生成后，这里会按轮次展示对照组和实验组输出。</div>
      ) : (
        rounds.map(([round, groupMap]) => {
          const questionItem = outputState.roundQuestionItems?.[round] || Object.values(groupMap)[0]?.questionItem;
          return (
          <div className="experiment-output-preview__round" key={round}>
            <div className="experiment-output-preview__round-title">
              第 {round} 轮
              {questionItemLabel(questionItem) ? <Tag color="geekblue">{questionItemLabel(questionItem)}</Tag> : null}
            </div>
            <div className="experiment-output-preview__round-info">
              <span>本轮问题：{outputState.roundQuestions[round] || Object.values(groupMap)[0]?.question || '暂无问题。'}</span>
              {questionItem?.expectedBehavior ? <Tag color="purple">预期边界行为：{expectedBehaviorLabel(questionItem.expectedBehavior)}</Tag> : null}
            </div>
            <div className="experiment-output-preview__groups">
              {plan.processGroups.map((group) => {
                const groupOutput = groupMap[group.id];
                const title = splitGroupName(group);
                return (
                  <div className="experiment-output-preview__group" key={group.id}>
                    <div className="experiment-output-preview__group-header">
                      <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{title.label}</Tag>
                      <Text strong>{title.title}</Text>
                      <Tag color={groupOutput?.status === 'done' ? 'green' : groupOutput?.status === 'terminated' ? 'orange' : groupOutput?.status === 'error' ? 'red' : groupOutput?.status === 'running' ? 'blue' : 'default'}>
                        {groupOutput?.status === 'done' ? '已完成' : groupOutput?.status === 'terminated' ? '已终止' : groupOutput?.status === 'error' ? '异常' : groupOutput?.status === 'running' ? '流式生成中' : '待生成'}
                      </Tag>
                    </div>
                    <div className="experiment-output-preview__question">{groupOutput?.question || '等待本组开始生成。'}</div>
                    <pre className="experiment-output-preview__text">
                      {groupOutput?.outputText || groupOutput?.streamingText || '暂无输出。'}
                    </pre>
                  </div>
                );
              })}
            </div>
          </div>
        );
        })
      )}
    </div>
  );
}

export function ExperimentEvaluationPanel({
  plan,
  evaluationPrompt,
  promptSource,
  outputState,
  evaluationState,
  runs,
  selectedRunId,
  evaluationRunning,
  evaluationConcurrency,
  compactMode,
  onUpdateEvaluationConcurrency,
  onSelectRun,
  onLoadRun,
  onRefreshRuns,
  onRunEvaluation,
  onToggleCompactMode
}: {
  plan: ExperimentPlan;
  evaluationPrompt: string;
  promptSource: string;
  outputState: ExperimentOutputState;
  evaluationState: ExperimentEvaluationState;
  runs: ExperimentRunSummary[];
  selectedRunId?: string;
  evaluationRunning: boolean;
  evaluationConcurrency: number;
  compactMode: boolean;
  onUpdateEvaluationConcurrency: (value: number) => void;
  onSelectRun: (runId: string) => void;
  onLoadRun: () => void;
  onRefreshRuns: () => void;
  onRunEvaluation: () => void;
  onToggleCompactMode: (value: boolean) => void;
}) {
  const rounds = Object.entries(evaluationState.scores).sort(([a], [b]) => Number(a) - Number(b));
  const groupAverageScores = getGroupAverageScores(plan, evaluationState);
  const evaluationRuns = runs.filter(hasEvaluationRecord);
  const selectedEvaluationRunId = hasEvaluationRecord(runs.find((run) => run.runId === selectedRunId)) ? selectedRunId : undefined;
  const [expandedRoundMap, setExpandedRoundMap] = useState<Record<string, boolean>>({});
  const isRoundExpanded = (round: string) => expandedRoundMap[round] ?? true;
  const allRoundsExpanded = Boolean(rounds.length) && rounds.every(([round]) => isRoundExpanded(round));
  const setAllRoundsExpanded = (expanded: boolean) => {
    setExpandedRoundMap(Object.fromEntries(rounds.map(([round]) => [round, expanded])));
  };
  const toggleRoundExpanded = (round: string) => {
    setExpandedRoundMap((prev) => ({ ...prev, [round]: !(prev[round] ?? true) }));
  };

  return (
    <div className="experiment-evaluation-panel">
      <div className="experiment-evaluation-panel__prompt">
        <div className="experiment-evaluation-panel__header">
          <Text strong>选择实验结果</Text>
          <Tag color={selectedRunId ? 'green' : 'default'}>{selectedRunId ? '已选择' : '未选择'}</Tag>
        </div>
        <div className="experiment-control-console__record-row is-evaluation">
          <Select
            allowClear
            placeholder="选择已保存实验结果"
            value={selectedRunId}
            onChange={(value) => onSelectRun(value || '')}
            options={runs.map((run) => ({
              value: run.runId,
              label: runRecordLabel(run)
            }))}
          />
          <Select
            allowClear
            placeholder="选择评估记录"
            value={selectedEvaluationRunId}
            onChange={(value) => onSelectRun(value || '')}
            options={evaluationRuns.map((run) => ({
              value: run.runId,
              label: evaluationRecordLabel(run)
            }))}
            notFoundContent="暂无评估记录"
          />
          <Button size="small" type="primary" disabled={!selectedRunId} loading={evaluationRunning} onClick={onRunEvaluation}>启动评估</Button>
          <Button size="small" onClick={onRefreshRuns}>刷新记录</Button>
          <Button size="small" disabled={!selectedRunId} onClick={onLoadRun}>载入结果</Button>
          <label className="experiment-evaluation-panel__concurrency">
            <Text type="secondary">评估并发</Text>
            <InputNumber
              size="small"
              min={1}
              max={getMaxEvaluationConcurrency()}
              value={evaluationConcurrency}
              onChange={(value) => onUpdateEvaluationConcurrency(Math.min(Number(value || 1), getMaxEvaluationConcurrency()))}
            />
          </label>
        </div>
      </div>

      <div className="experiment-evaluation-panel__prompt">
        <div className="experiment-evaluation-panel__header">
          <Text strong>本实验评估提示词</Text>
          <Tag color="cyan">{promptSource}</Tag>
        </div>
        <Paragraph className="experiment-evaluation-panel__prompt-text">
          {evaluationPrompt || '正在加载本实验评估提示词...'}
        </Paragraph>
      </div>

      <div className="experiment-evaluation-panel__progress">
        <div className="experiment-evaluation-panel__header">
          <Text strong>评估进度</Text>
          {evaluationState.current ? (
            <Tag color="blue">正在评估第 {evaluationState.current.round} 轮 · {evaluationState.current.groupLabel}</Tag>
          ) : (
            <Tag>{evaluationState.status === 'done' ? '评估完成' : '待启动评估'}</Tag>
          )}
          {groupAverageScores.map(({ group, average }) => {
            const title = splitGroupName(group);
            return typeof average === 'number' ? (
              <Tag color={getScoreTagColor(average)} key={group.id}>{title.label} 平均 {formatScore(average)}/10</Tag>
            ) : null;
          })}
          {rounds.length ? (
            <Button size="small" onClick={() => setAllRoundsExpanded(!allRoundsExpanded)}>
              {allRoundsExpanded ? '收回全部卡片' : '展开全部卡片'}
            </Button>
          ) : null}
          {rounds.length ? (
            <Button size="small" type={compactMode ? 'primary' : 'default'} onClick={() => onToggleCompactMode(!compactMode)}>
              {compactMode ? '退出精简模式' : '精简模式'}
            </Button>
          ) : null}
        </div>
        <Progress percent={evaluationState.progress} size="small" status={getProgressStatus(evaluationState.status === 'error' ? 'error' : evaluationState.status === 'done' ? 'done' : evaluationState.status === 'running' ? 'running' : 'idle')} />
        {evaluationState.message ? <Text type="danger">{evaluationState.message}</Text> : null}
      </div>

      {rounds.length === 0 ? (
        <div className="experiment-output-preview__empty">点击“启动评估”后，这里会展示每一轮、每一组的得分。</div>
      ) : compactMode ? (
        <div className="experiment-evaluation-panel__compact-list">
          {rounds.map(([round, groupMap]) => {
            const outputGroupMap = outputState.rounds[round] || {};
            const questionItem = outputState.roundQuestionItems?.[round] || Object.values(outputGroupMap)[0]?.questionItem;
            const groupLabel = questionItemLabel(questionItem);
            return (
              <div className="experiment-evaluation-panel__compact-card" key={round}>
                <div className="experiment-evaluation-panel__compact-title">
                  <strong>第 {round} 轮</strong>
                  {groupLabel ? <Tag color="geekblue">{groupLabel}</Tag> : null}
                </div>
                <div className="experiment-evaluation-panel__compact-groups">
                  {plan.processGroups.map((group) => {
                    const score = groupMap[group.id];
                    const displayScore = getEvaluationDisplayScore(score);
                    const title = splitGroupName(group);
                    return (
                      <div className="experiment-evaluation-panel__compact-row" key={group.id}>
                        <span>{title.label} · {title.title}</span>
                        <Tag color={score?.status === 'done' ? getScoreTagColor(displayScore) : score?.status === 'error' ? 'red' : score?.status === 'running' ? 'blue' : 'default'}>
                          {score?.status === 'done' ? `${formatScore(displayScore)}/10` : score?.status === 'error' ? '异常' : score?.status === 'running' ? '评估中' : '待评估'}
                        </Tag>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        rounds.map(([round, groupMap]) => {
          const outputGroupMap = outputState.rounds[round] || {};
          const questionItem = outputState.roundQuestionItems?.[round] || Object.values(outputGroupMap)[0]?.questionItem;
          const questionText = outputState.roundQuestions[round] || Object.values(outputGroupMap)[0]?.question || '暂无问题。';
          const groupLabel = questionItemLabel(questionItem);
          const roundExpanded = isRoundExpanded(round);
          return (
          <div className="experiment-evaluation-panel__round" key={round}>
            <div className="experiment-output-preview__round-title">
              第 {round} 轮
              {groupLabel ? <Tag color="geekblue">{groupLabel}</Tag> : null}
              <Button size="small" onClick={() => toggleRoundExpanded(round)}>
                {roundExpanded ? '收回本轮' : '展开本轮'}
              </Button>
            </div>
            <div className="experiment-output-preview__round-info">
              <span>本轮问题：{questionText}</span>
              {questionItem?.expectedBehavior ? <Tag color="purple">预期边界行为：{expectedBehaviorLabel(questionItem.expectedBehavior)}</Tag> : null}
            </div>
            <div className="experiment-evaluation-panel__score-grid">
              {plan.processGroups.map((group) => {
                const score = groupMap[group.id];
                const displayScore = getEvaluationDisplayScore(score);
                const title = splitGroupName(group);
                const subscores = getStructuredSubscores(score?.structuredEvaluation);
                return (
                  <div className="experiment-evaluation-panel__score-card" key={group.id}>
                    <div className="experiment-output-preview__group-header">
                      <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{title.label}</Tag>
                      <Text strong>{title.title}</Text>
                      <Tag color={score?.status === 'done' ? getScoreTagColor(displayScore) : score?.status === 'error' ? 'red' : score?.status === 'running' ? 'blue' : 'default'}>
                        {score?.status === 'done' ? `${formatScore(displayScore)}/10` : score?.status === 'error' ? '异常' : score?.status === 'running' ? '评估中' : '待评估'}
                      </Tag>
                    </div>
                    {roundExpanded ? (
                    <>
                    <div className="experiment-evaluation-panel__structured">
                      <Text type="secondary">结构化评估</Text>
                      {score?.structuredEvaluation ? (
                        <>
                          <div className="experiment-evaluation-panel__score-summary">
                            <div>
                              <Text type="secondary">格式化分数</Text>
                              <div className={`experiment-evaluation-panel__score-number is-${String(score.structuredEvaluation.verdict || 'unknown')}`}>
                                {score.structuredEvaluation.score_text || `${formatScore(score.structuredEvaluation.score)}/10`}
                              </div>
                            </div>
                            <Tag color={getVerdictColor(String(score.structuredEvaluation.verdict || ''))}>
                              {getVerdictText(String(score.structuredEvaluation.verdict || ''))}
                            </Tag>
                            {score.structuredEvaluation.needs_review ? <Tag color="orange">需复核</Tag> : null}
                          </div>
                          {score.structuredEvaluation.summary ? (
                            <div className="experiment-evaluation-panel__score-summary-text">{String(score.structuredEvaluation.summary)}</div>
                          ) : null}
                          {subscores.length ? (
                            <Collapse
                              size="small"
                              className="experiment-evaluation-panel__detail-collapse"
                              items={[
                                {
                                  key: 'subscores',
                                  label: `分项打分（${subscores.length} 项）`,
                                  children: (
                                    <div className="experiment-evaluation-panel__subscores">
                                      {subscores.map((item, index) => (
                                        <div className="experiment-evaluation-panel__subscore" key={`${String(item.name || item.label || index)}-${index}`}>
                                          <span>{String(item.name || item.label || `分项 ${index + 1}`)}</span>
                                          <strong>{formatScoreText(item.score, item.max_score ?? item.maxScore ?? 10)}</strong>
                                          {item.reason ? <em>{String(item.reason)}</em> : null}
                                        </div>
                                      ))}
                                    </div>
                                  )
                                }
                              ]}
                            />
                          ) : null}
                        </>
                      ) : score?.structuredError ? (
                        <Text type="danger">{score.structuredError}</Text>
                      ) : (
                        <Text type="secondary">等待结构化结果。</Text>
                      )}
                    </div>
                    {score?.structuredEvaluation ? (
                      <Collapse
                        size="small"
                        className="experiment-evaluation-panel__detail-collapse experiment-evaluation-panel__json-collapse"
                        items={[
                          {
                            key: 'json',
                            label: '原始 JSON',
                            children: (
                              <pre className="experiment-evaluation-panel__json-text">
                                {formatStructuredEvaluation(score.structuredEvaluation)}
                              </pre>
                            )
                          }
                        ]}
                      />
                    ) : null}
                    <Collapse
                      size="small"
                      className="experiment-evaluation-panel__detail-collapse"
                      items={[
                        {
                          key: 'comment',
                          label: '自然语言评估',
                          children: <div className="experiment-evaluation-panel__comment">{score?.comment || '暂无评估说明。'}</div>
                        }
                      ]}
                    />
                    </>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        );
        })
      )}
    </div>
  );
}
