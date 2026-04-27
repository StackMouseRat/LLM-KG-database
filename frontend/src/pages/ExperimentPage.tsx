import { Button, Card, Collapse, InputNumber, Popover, Progress, Segmented, Select, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ALL_MULTI_FAULT_QUESTIONS, ALL_SINGLE_FAULT_QUESTIONS, EXPERIMENT_QUESTION_GROUPS } from '../data/presetQuestions';
import { ExperimentQuestionPopover } from '../features/experiment/ExperimentQuestionPopover';
import { fetchExperimentQuestionSuite, fetchExperimentRunDetail, fetchExperimentRuns, saveExperimentEvaluation, type ExperimentQuestionItem, type ExperimentQuestionSuite, type ExperimentRunSummary } from '../features/experiment/experimentApi';
import { fetchTemplatePrompts } from '../features/quality/qualityApi';
import { loadPromptCache, savePromptCache } from '../features/quality/qualityStorage';

const { Paragraph, Text, Title } = Typography;

type ExperimentStepStatus = 'pending' | 'running' | 'done' | 'failed';
type ExperimentCardView = 'info' | 'control' | 'preview' | 'evaluation';
type ExperimentControlStage = 'generation' | 'evaluation';
type ExperimentStageState = {
  status: 'idle' | 'running' | 'done' | 'error';
  progress: number;
  message?: string;
};

type ExperimentControlState = {
  runCount: number;
  concurrency: number;
  evaluationConcurrency: number;
  generation: ExperimentStageState;
  evaluation: ExperimentStageState;
};

type ExperimentGroupOutput = {
  groupId: string;
  groupLabel: string;
  question: string;
  questionItem?: ExperimentQuestionItem;
  outputText: string;
  streamingText: string;
  status: 'running' | 'done' | 'terminated' | 'error';
};

type ExperimentActiveGroup = {
  key: string;
  round: number;
  groupId: string;
  groupLabel: string;
};

type ExperimentOutputState = {
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

type ExperimentEvaluationScore = {
  groupId: string;
  groupLabel: string;
  score?: number;
  structuredEvaluation?: Record<string, any>;
  structuredError?: string;
  status: 'pending' | 'running' | 'done' | 'error';
  comment?: string;
};

type ExperimentEvaluationState = {
  status: 'idle' | 'running' | 'done' | 'error';
  progress: number;
  current?: {
    round: number;
    groupId: string;
    groupLabel: string;
  };
  scores: Record<string, Record<string, ExperimentEvaluationScore>>;
  message?: string;
};

type ExperimentEvaluationTask = {
  round: number;
  group: ExperimentProcessGroup;
  output: ExperimentGroupOutput;
};

type ExperimentGroupProgress = {
  activeStepIndex?: number;
  completedStepIndexes?: number[];
  failedStepIndex?: number;
};

type ExperimentPlanProgress = Partial<Record<string, ExperimentGroupProgress>>;
type ExperimentProgressByPlan = Partial<Record<string, ExperimentPlanProgress>>;

type ExperimentFlowNode = {
  plugin: string;
  input: string;
  output: string;
  mode?: '主链路' | '并发分支' | '逐章并发' | '逐故障并发';
  variables?: string[];
  connectsToNext?: boolean;
};

type SupportLayerTag = '图谱' | '模板' | '案例' | '工作流';

type ExperimentProcessGroup = {
  id: string;
  role: '对照组' | '实验组';
  name: string;
  summary: string;
  supportTags?: SupportLayerTag[];
  nodes: ExperimentFlowNode[];
};

type ExperimentPlan = {
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

const experimentStepStatusText: Record<ExperimentStepStatus, string> = {
  pending: '待运行',
  running: '进行中',
  done: '已完成',
  failed: '异常'
};

const defaultStageState: ExperimentStageState = {
  status: 'idle',
  progress: 0
};

const defaultControlState: ExperimentControlState = {
  runCount: 4,
  concurrency: 2,
  evaluationConcurrency: 2,
  generation: defaultStageState,
  evaluation: defaultStageState
};

const defaultOutputState: ExperimentOutputState = {
  activeGroups: [],
  roundQuestions: {},
  roundQuestionItems: {},
  rounds: {}
};

const defaultEvaluationState: ExperimentEvaluationState = {
  status: 'idle',
  progress: 0,
  scores: {}
};

const BOUNDARY_QUESTION_SUITE_ID = 'boundary_input_boundary_v1';
const DISAMBIGUATION_QUESTION_SUITE_ID = 'disambiguation_device_subject_v1';

const node = (
  plugin: string,
  input: string,
  output: string,
  variables: string[] = [],
  mode: ExperimentFlowNode['mode'] = '主链路',
  connectsToNext = true
): ExperimentFlowNode => ({
  plugin,
  input,
  output,
  mode,
  variables,
  connectsToNext
});

const completeWorkflowNodes = [
  node('基本信息获取', '用户问题', '边界判定结果、边界判定信息、用户问题、故障与场景提取结果、知识库名、图谱检索方案素材', ['保留：边界判定结果/边界判定信息', '保留：图谱检索方案素材']),
  node('模板切片', '当前模板配置', '章节列表、章节标题、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
  node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文')
];

const completeWorkflowGroup: ExperimentProcessGroup = {
  id: 'control',
  role: '对照组',
  name: '完整流程',
  summary: '完整链路基线。',
  supportTags: ['图谱', '模板', '工作流'],
  nodes: completeWorkflowNodes
};

// 后续接入批量运行接口后，将接口返回的 planId/groupId/stepIndex 写入这里即可驱动流程状态。
const experimentProgressByPlan: ExperimentProgressByPlan = {};

function getExperimentStepStatus(progress: ExperimentPlanProgress | undefined, groupId: string, stepIndex: number): ExperimentStepStatus {
  const groupProgress = progress?.[groupId];
  if (groupProgress?.failedStepIndex === stepIndex) return 'failed';
  if (groupProgress?.activeStepIndex === stepIndex) return 'running';
  if (groupProgress?.completedStepIndexes?.includes(stepIndex)) return 'done';
  return 'pending';
}

const experimentPlans: ExperimentPlan[] = [
  {
    id: 'boundary',
    title: '输入边界实验',
    tag: '边界',
    objective: '验证当前工作流能在生成前识别无关问题、不支持设备和设备-故障错配输入，避免继续生成伪预案。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-no-boundary',
        role: '实验组',
        name: '实验组一：移除输入边界校验',
        summary: '不使用边界判定。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['移除边界判定']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文')
        ]
      },
      {
        id: 'exp-keyword-boundary',
        role: '实验组',
        name: '实验组二：关键词边界校验',
        summary: '关键词替代边界判定。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '用户问题 + 关键词预筛结果', '故障与场景提取结果、知识库名、图谱检索方案素材', ['关键词替代边界判定']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文')
        ]
      },
    ],
    questionSuiteId: BOUNDARY_QUESTION_SUITE_ID,
    inputs: ['今天吃什么？', '发电机转子接地故障，请生成应急方案。', '变压器拒动，请生成应急方案。'],
    expectedInput: '非电力问题、不支持设备问题、设备和动作明显不兼容的问题。',
    expectedOutput: ['异常输入应被终止并给出边界判定结果/边界判定信息。', '后续模板切片、图谱检索和章节生成不应启动。', '实验组用于观察误放行、伪预案和错误正文长度。'],
    metrics: ['终止准确率', '提示可读性', '伪预案避免率', '后续链路阻断率']
  },
  {
    id: 'disambiguation',
    title: '设备主体消歧实验',
    tag: '消歧',
    objective: '验证当前工作流能从位置修饰词、保护动作来源和伴随告警中识别真正故障主体。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-drop-subject-judgement',
        role: '实验组',
        name: '实验组一：移除主体判定',
        summary: '移除主体判定。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '混淆类用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['移除主体判定']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文')
        ]
      },
      {
        id: 'exp-keyword-subject-judgement',
        role: '实验组',
        name: '实验组二：关键词主体判定',
        summary: '关键词匹配主体判定。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '混淆类用户问题 + 关键词匹配结果', '故障与场景提取结果、知识库名、图谱检索方案素材', ['关键词替代主体判定']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文')
        ]
      },
    ],
    questionSuiteId: DISAMBIGUATION_QUESTION_SUITE_ID,
    inputs: ['主变旁110kV断路器保护发令后无法分闸，请生成应急处置方案。', '开关柜内电流互感器二次开路，电流表指示接近零，请生成现场方案。', '线路侧避雷器雨后出现放电痕迹并损坏，请生成应急方案。'],
    expectedInput: '包含多个设备名或位置修饰词，但只有一个真实故障主体的问题。',
    expectedOutput: ['输出应围绕真正故障主体展开。', '知识库和故障二级节点应与主体一致。', '实验组用于观察移除主体判定和关键词主体判定造成的主体漂移。'],
    metrics: ['设备识别正确率', '知识库命中率', '故障二级节点准确率', '正文主体一致性']
  },
  {
    id: 'graphTemplate',
    title: '图谱与模板约束实验',
    tag: '图谱/模板',
    objective: '验证图谱事实和模板章节约束对预案事实完整性与结构规范性的共同作用。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-no-graph',
        role: '实验组',
        name: '实验组一：移除图谱',
        summary: '移除图谱素材。',
        supportTags: ['模板', '工作流'],
        nodes: [
          node('基本信息获取', '图谱与模板依赖类用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['移除：图谱检索方案素材']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 章节模板文本', '预案正文')
        ]
      },
      {
        id: 'exp-no-template',
        role: '实验组',
        name: '实验组二：移除模板',
        summary: '移除模板约束。',
        supportTags: ['图谱', '工作流'],
        nodes: [
          node('基本信息获取', '图谱与模板依赖类用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材'),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['移除']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材', '预案正文', ['移除：章节模板文本'])
        ]
      },
    ],
    inputs: ['雨后某220kV避雷器出现放电痕迹并伴随泄漏电流异常升高，请生成应急处置方案。', '断路器保护发令后未动作，现场未见分闸，请生成包含检查确认和抢修措施的方案。', '某电缆接头击穿起火，请生成包含响应终止和恢复验证的完整预案。'],
    expectedInput: '同时依赖图谱事实补充和模板章节约束的正式预案生成问题。',
    expectedOutput: ['对照组应兼顾事实覆盖和章节结构。', '移除图谱组用于观察原因、措施、风险和资源缺口。', '移除模板组用于观察章节缺失、重复和串章。'],
    metrics: ['事实覆盖度', '措施覆盖度', '章节完整率', '章节边界稳定性']
  },
  {
    id: 'multiFault',
    title: '多故障链式实验',
    tag: '链式',
    objective: '验证多故障模式能识别链式或并发故障，并将逐故障图谱检索结果融合进统一处置方案。',
    processGroups: [
      {
        ...completeWorkflowGroup,
        nodes: [
          node('多故障基本信息获取', '多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果', ['保留：多个故障对象']),
          node('逐故障图谱检索', '设备表 + 故障列表', '逐故障图谱检索素材', ['逐故障并发查询图谱'], '逐故障并发'),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 逐故障图谱检索素材 + 章节模板文本', '预案正文', ['保留：主次故障融合'])
        ]
      },
      {
        id: 'exp-single-fault',
        role: '实验组',
        name: '实验组一：单故障普通链路',
        summary: '强制单故障。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '多故障用户问题', '单一故障场景、知识库名、图谱检索方案素材', ['仅单故障']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['仅主故障'])
        ]
      },
      {
        id: 'exp-detect-no-per-fault-graph',
        role: '实验组',
        name: '实验组二：仅主故障图谱',
        summary: '保留多故障识别，只检索主故障图谱。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('多故障基本信息获取', '多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果'),
          node('主故障图谱检索', '设备表 + 主故障', '主故障图谱检索方案素材', ['仅主故障图谱']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障列表 + 主故障图谱检索方案素材 + 章节模板文本', '预案正文', ['无次生图谱'])
        ]
      },
    ],
    inputs: ['吊车碰线后线路跳闸，通信光缆同时中断，保护通道异常，请生成处置预案。', '暴雨后电缆沟进水，电缆接头绝缘告警，同时环网柜出现凝露和局放异常，请生成应急方案。', '输电线路山火跳闸后，光缆通信中断，远方保护通道退出，请生成应急处置方案。'],
    expectedInput: '一个场景中出现多个设备、多个故障或先后诱发关系的问题。',
    expectedOutput: ['输出应识别多个故障。', '输出应区分主故障、伴随故障和受影响业务。', '实验组用于观察次生故障遗漏和素材拼接冲突。'],
    metrics: ['故障拆解率', '主次识别正确率', '逐故障图谱覆盖率', '融合处置完整度']
  }
];

function ExperimentSection({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`experiment-plan-card__section${wide ? ' is-wide' : ''}`}>
      <Text strong>{title}</Text>
      {children}
    </div>
  );
}

function getRuntimeChanges(group: ExperimentProcessGroup, node: ExperimentFlowNode) {
  if (group.role === '对照组') return [];
  return node.variables && node.variables.length > 0
    ? node.variables
        .map((variable) => variable.replace('调用并行生成插件', ''))
        .filter((variable) => !variable.startsWith('无上游变量'))
    : [];
}

function splitGroupName(group: ExperimentProcessGroup) {
  const parts = group.name.split('：');
  if (group.role === '实验组' && parts.length > 1) {
    return { label: parts[0], title: parts.slice(1).join('：') };
  }
  return { label: group.role, title: group.name };
}

function getSupportLayerTags(group: ExperimentProcessGroup) {
  return group.supportTags ?? [];
}

function getActiveControlStage(state: ExperimentControlState) {
  return state.evaluation.status !== 'idle' ? state.evaluation : state.generation;
}

function getStageStatusText(status: ExperimentStageState['status']) {
  if (status === 'idle') return '待启动';
  if (status === 'running') return '运行中';
  if (status === 'done') return '已完成';
  return '异常';
}

function getProgressStatus(status: ExperimentStageState['status']) {
  if (status === 'running') return 'active';
  if (status === 'done') return 'success';
  if (status === 'error') return 'exception';
  return 'normal';
}

function getSuiteQuestionItems(suite: ExperimentQuestionSuite | undefined): ExperimentQuestionItem[] {
  return suite?.groups.flatMap((group) => group.questions
    .filter((question) => question.enabled)
    .map((question) => ({
      questionId: question.questionId,
      questionText: question.questionText,
      groupId: group.groupId,
      groupCode: group.code,
      groupName: group.name,
      expectedBehavior: question.expectedBehavior || group.expectedBehavior,
      category: question.category || group.name
    }))) || [];
}

function pickRandomQuestionItems(questions: ExperimentQuestionItem[], count: number) {
  return [...questions]
    .sort(() => Math.random() - 0.5)
    .slice(0, count);
}

function questionItemLabel(item?: ExperimentQuestionItem) {
  if (!item) return '';
  return [item.groupCode, item.groupName].filter(Boolean).join(' · ');
}

function eventQuestionItem(data: any): ExperimentQuestionItem | undefined {
  return data?.questionItem && typeof data.questionItem === 'object' && String(data.questionItem.questionText || '').trim()
    ? data.questionItem as ExperimentQuestionItem
    : undefined;
}

function mergeRoundQuestionItem(current: ExperimentOutputState, roundKey: string, item?: ExperimentQuestionItem) {
  return item ? { ...(current.roundQuestionItems || {}), [roundKey]: item } : current.roundQuestionItems;
}

function getMaxExperimentConcurrency(runCount: number, groupCount: number) {
  return Math.max(1, Math.min(15, Math.max(1, runCount) * Math.max(1, groupCount)));
}

function getMaxEvaluationConcurrency() {
  return 10;
}

function activeGroupKey(round: number, groupId: string) {
  return `${round}:${groupId}`;
}

function addActiveGroup(current: ExperimentOutputState, group: Omit<ExperimentActiveGroup, 'key'>) {
  const key = activeGroupKey(group.round, group.groupId);
  const activeGroups = (current.activeGroups || []).filter((item) => item.key !== key);
  return [...activeGroups, { ...group, key }].sort((a, b) => a.round - b.round || a.groupLabel.localeCompare(b.groupLabel));
}

function removeActiveGroup(current: ExperimentOutputState, round: number, groupId: string) {
  const key = activeGroupKey(round, groupId);
  return (current.activeGroups || []).filter((item) => item.key !== key);
}

function buildGroupProgress(group: ExperimentProcessGroup, state: ExperimentControlState) {
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

function ExperimentFlowDiagram({ planId, group, progress, showStatus = true }: { planId: string; group: ExperimentProcessGroup; progress?: ExperimentGroupProgress; showStatus?: boolean }) {
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

function ExperimentControlPanel({
  plan,
  state,
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
  const generationRunning = state.generation.status === 'running';
  const evaluationRunning = state.evaluation.status === 'running';
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
          <Progress percent={state.evaluation.progress} size="small" status={getProgressStatus(state.evaluation.status)} />
          <Text type="secondary">先选择并载入某次实验结果，再对该结果进行自动评估。</Text>
          {state.evaluation.message ? <Text type="danger">{state.evaluation.message}</Text> : null}
        </div>
      </div>

      <div className="experiment-control-console__log">
        <Text type="secondary">实时进度</Text>
        <div>生成：{getStageStatusText(state.generation.status)} · {state.generation.progress}%</div>
        <div>评估：{getStageStatusText(state.evaluation.status)} · {state.evaluation.progress}%</div>
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

function ExperimentOutputPreview({
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
            <div className="experiment-output-preview__round-question">本轮问题：{outputState.roundQuestions[round] || Object.values(groupMap)[0]?.question || '暂无问题。'}</div>
            {questionItem?.expectedBehavior ? (
              <div className="experiment-output-preview__round-meta">预期边界行为：{questionItem.expectedBehavior}</div>
            ) : null}
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

function getAverageScore(evaluationState: ExperimentEvaluationState) {
  const values = Object.values(evaluationState.scores)
    .flatMap((groupMap) => Object.values(groupMap))
    .map((item) => item.score)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
  if (!values.length) return undefined;
  return Math.round((values.reduce((sum, score) => sum + score, 0) / values.length) * 10) / 10;
}

function formatStructuredEvaluation(value?: Record<string, any>) {
  if (!value) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function getVerdictColor(verdict?: string) {
  if (verdict === 'pass') return 'green';
  if (verdict === 'partial') return 'gold';
  if (verdict === 'fail') return 'red';
  return 'default';
}

function getVerdictText(verdict?: string) {
  if (verdict === 'pass') return '通过';
  if (verdict === 'partial') return '部分通过';
  if (verdict === 'fail') return '不通过';
  return '未知';
}

function getStructuredSubscores(value?: Record<string, any>) {
  const subscores = value?.subscores;
  return Array.isArray(subscores) ? subscores.filter((item) => item && typeof item === 'object') : [];
}

function runRecordLabel(run: ExperimentRunSummary) {
  const generation = `${run.completedGroups}/${run.totalGroups}`;
  const evaluation = run.totalEvaluations ? ` · 评估 ${run.evaluatedGroups || 0}/${run.totalEvaluations}` : '';
  return `${run.name || `总次数${run.runCount} · 并发${run.concurrency}`} · 生成 ${generation}${evaluation} · ${run.updatedAt || run.runId}`;
}

function evaluationRecordLabel(run: ExperimentRunSummary) {
  const evaluation = run.totalEvaluations ? `${run.evaluatedGroups || 0}/${run.totalEvaluations}` : '0/0';
  return `${run.name || `总次数${run.runCount} · 并发${run.concurrency}`} · 评估 ${evaluation} · ${run.evaluationUpdatedAt || run.updatedAt || run.runId}`;
}

function hasEvaluationRecord(run?: ExperimentRunSummary) {
  return Boolean(run?.evaluationUpdatedAt || run?.totalEvaluations || run?.evaluationStatus && run.evaluationStatus !== 'idle');
}

function ExperimentEvaluationPanel({
  plan,
  evaluationPrompt,
  promptSource,
  evaluationState,
  runs,
  selectedRunId,
  evaluationRunning,
  evaluationConcurrency,
  onUpdateEvaluationConcurrency,
  onSelectRun,
  onLoadRun,
  onRefreshRuns,
  onRunEvaluation
}: {
  plan: ExperimentPlan;
  evaluationPrompt: string;
  promptSource: string;
  evaluationState: ExperimentEvaluationState;
  runs: ExperimentRunSummary[];
  selectedRunId?: string;
  evaluationRunning: boolean;
  evaluationConcurrency: number;
  onUpdateEvaluationConcurrency: (value: number) => void;
  onSelectRun: (runId: string) => void;
  onLoadRun: () => void;
  onRefreshRuns: () => void;
  onRunEvaluation: () => void;
}) {
  const rounds = Object.entries(evaluationState.scores).sort(([a], [b]) => Number(a) - Number(b));
  const averageScore = getAverageScore(evaluationState);
  const evaluationRuns = runs.filter(hasEvaluationRecord);
  const selectedEvaluationRunId = hasEvaluationRecord(runs.find((run) => run.runId === selectedRunId)) ? selectedRunId : undefined;

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
          {typeof averageScore === 'number' ? <Tag color="green">平均分 {averageScore}/10</Tag> : null}
        </div>
        <Progress percent={evaluationState.progress} size="small" status={getProgressStatus(evaluationState.status === 'error' ? 'error' : evaluationState.status === 'done' ? 'done' : evaluationState.status === 'running' ? 'running' : 'idle')} />
        {evaluationState.message ? <Text type="danger">{evaluationState.message}</Text> : null}
      </div>

      {rounds.length === 0 ? (
        <div className="experiment-output-preview__empty">点击“启动评估”后，这里会展示每一轮、每一组的得分。</div>
      ) : (
        rounds.map(([round, groupMap]) => (
          <div className="experiment-evaluation-panel__round" key={round}>
            <div className="experiment-output-preview__round-title">第 {round} 轮</div>
            <div className="experiment-evaluation-panel__score-grid">
              {plan.processGroups.map((group) => {
                const score = groupMap[group.id];
                const title = splitGroupName(group);
                return (
                  <div className="experiment-evaluation-panel__score-card" key={group.id}>
                    <div className="experiment-output-preview__group-header">
                      <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{title.label}</Tag>
                      <Text strong>{title.title}</Text>
                      <Tag color={score?.status === 'done' ? 'green' : score?.status === 'error' ? 'red' : score?.status === 'running' ? 'blue' : 'default'}>
                        {score?.status === 'done' ? `${score.score ?? '-'}/10` : score?.status === 'error' ? '异常' : score?.status === 'running' ? '评估中' : '待评估'}
                      </Tag>
                    </div>
                    <div className="experiment-evaluation-panel__structured">
                      <Text type="secondary">结构化评估</Text>
                      {score?.structuredEvaluation ? (
                        <>
                          <div className="experiment-evaluation-panel__score-summary">
                            <div>
                              <Text type="secondary">格式化分数</Text>
                              <div className="experiment-evaluation-panel__score-number">
                                {score.structuredEvaluation.score_text || `${score.structuredEvaluation.score ?? '-'}/10`}
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
                          {getStructuredSubscores(score.structuredEvaluation).length ? (
                            <div className="experiment-evaluation-panel__subscores">
                              {getStructuredSubscores(score.structuredEvaluation).map((item, index) => (
                                <div className="experiment-evaluation-panel__subscore" key={`${String(item.name || item.label || index)}-${index}`}>
                                  <span>{String(item.name || item.label || `分项 ${index + 1}`)}</span>
                                  <strong>{String(item.score ?? '-')}/{String(item.max_score ?? item.maxScore ?? '-')}</strong>
                                  {item.reason ? <em>{String(item.reason)}</em> : null}
                                </div>
                              ))}
                            </div>
                          ) : null}
                          <Collapse
                            size="small"
                            className="experiment-evaluation-panel__json-collapse"
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
                        </>
                      ) : score?.structuredError ? (
                        <Text type="danger">{score.structuredError}</Text>
                      ) : (
                        <Text type="secondary">等待结构化结果。</Text>
                      )}
                    </div>
                    <div className="experiment-evaluation-panel__comment">{score?.comment || '暂无评估说明。'}</div>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function parseEvaluationScore(text: string) {
  const scoreMatch = text.match(/(\d+(?:\.\d+)?)\s*\/\s*10/) || text.match(/(?:总分|得分|评分|score)\D{0,12}(\d+(?:\.\d+)?)/i);
  if (!scoreMatch) return undefined;
  const score = Number(scoreMatch[1]);
  if (!Number.isFinite(score)) return undefined;
  return Math.max(0, Math.min(10, score));
}

async function runEvaluationRequest(
  prompt: string,
  content: string,
  context: { question: string; questionGroup?: string; groupLabel: string; groupTitle: string; round: number },
  onUpdate?: (patch: Partial<Pick<ExperimentEvaluationScore, 'comment' | 'score' | 'structuredEvaluation' | 'structuredError'>>) => void
) {
  const experimentGroup = `${context.groupLabel} ${context.groupTitle}`.trim();
  const scoringPrompt = `${prompt}\n\n当前评估样本：\n- 轮次：第 ${context.round} 轮\n- 题目分组：${context.questionGroup || '未提供'}\n- 实验组：${context.groupLabel} ${context.groupTitle}\n- 用户问题：${context.question}\n\n请基于上述用户问题、题目分组、实验组和当前输出进行10分制打分。必须在最终答案最后一行输出“总分：N/10”。`;
  const response = await fetch('/api/quality/review', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      stream: true,
      mode: 'evaluate',
      structured: true,
      structuredContext: {
        question: context.question,
        questionGroup: context.questionGroup || '',
        experimentGroup
      },
      prompt: scoringPrompt,
      content
    })
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let outputText = '';
  let structuredEvaluation: Record<string, any> | undefined;
  let structuredError = '';

  const applyOutput = (text: string) => {
    outputText = text;
    onUpdate?.({ comment: outputText || '评估中...', score: parseEvaluationScore(outputText) });
  };

  const flushEvent = (rawChunk: string) => {
    const lines = rawChunk.split('\n').map((line) => line.trim()).filter(Boolean);
    let eventName = '';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!eventName || eventName === 'close') return;
    const dataText = dataLines.join('\n');
    let data: any = {};
    if (dataText) {
      try {
        data = JSON.parse(dataText);
      } catch {
        data = dataText;
      }
    }
    if (eventName === 'quality_output_chunk') {
      applyOutput(`${outputText}${String(data?.chunk || '')}`);
      return;
    }
    if (eventName === 'quality_done') {
      applyOutput(String(data?.output_text || outputText));
      return;
    }
    if (eventName === 'quality_structured_done') {
      structuredEvaluation = data?.structured_evaluation && typeof data.structured_evaluation === 'object'
        ? data.structured_evaluation as Record<string, any>
        : undefined;
      const structuredScore = Number(structuredEvaluation?.score);
      onUpdate?.({
        structuredEvaluation,
        structuredError: undefined,
        score: Number.isFinite(structuredScore) ? Math.max(0, Math.min(10, structuredScore)) : parseEvaluationScore(outputText)
      });
      return;
    }
    if (eventName === 'quality_structured_error') {
      structuredError = String(data?.message || '结构化评估失败');
      onUpdate?.({ structuredError });
      return;
    }
    if (eventName === 'quality_error') {
      throw new Error(data?.message || '评估插件执行失败');
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    parts.forEach((part) => part.trim() && flushEvent(part));
  }
  if (buffer.trim()) flushEvent(buffer);

  const structuredScore = Number(structuredEvaluation?.score);
  return {
    score: Number.isFinite(structuredScore) ? Math.max(0, Math.min(10, structuredScore)) : parseEvaluationScore(outputText),
    comment: outputText || '评估完成，但未返回说明。',
    structuredEvaluation,
    structuredError: structuredError || undefined
  };
}

async function streamExperimentRun(
  payload: {
    planId: string;
    stage: ExperimentControlStage;
    runCount: number;
    concurrency: number;
    questions: string[];
    questionItems: ExperimentQuestionItem[];
    runId?: string;
  },
  onEvent: (eventName: string, data: any) => void
) {
  const response = await fetch('/api/experiment/run', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify({ ...payload, stream: true })
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    let message = text || `请求失败：${response.status}`;
    try {
      const parsed = JSON.parse(text);
      message = parsed?.message || message;
    } catch {}
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const flushEvent = (rawChunk: string) => {
    const lines = rawChunk.split('\n').map((line) => line.trim()).filter(Boolean);
    let eventName = '';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!eventName || eventName === 'close') return;
    const dataText = dataLines.join('\n');
    let data: any = {};
    if (dataText) {
      try {
        data = JSON.parse(dataText);
      } catch {
        data = dataText;
      }
    }
    onEvent(eventName, data);
    if (eventName === 'experiment_error') {
      throw new Error(data?.message || '实验执行失败');
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    parts.forEach((part) => part.trim() && flushEvent(part));
  }
  if (buffer.trim()) flushEvent(buffer);
}

export function ExperimentPage() {
  const experimentQuestionCount = EXPERIMENT_QUESTION_GROUPS.reduce((total, group) => total + group.questions.length, 0);
  const [evaluationPrompt, setEvaluationPrompt] = useState(() => loadPromptCache()?.find((item) => item.prompt_key === 'evaluate_prompt')?.prompt_text || '');
  const [cardViewMap, setCardViewMap] = useState<Record<string, ExperimentCardView>>({});
  const [controlStateMap, setControlStateMap] = useState<Record<string, ExperimentControlState>>({});
  const [outputStateMap, setOutputStateMap] = useState<Record<string, ExperimentOutputState>>({});
  const [evaluationStateMap, setEvaluationStateMap] = useState<Record<string, ExperimentEvaluationState>>({});
  const [questionSuiteMap, setQuestionSuiteMap] = useState<Record<string, ExperimentQuestionSuite>>({});
  const [questionSuiteErrorMap, setQuestionSuiteErrorMap] = useState<Record<string, string>>({});
  const [sampledQuestionMap, setSampledQuestionMap] = useState<Record<string, ExperimentQuestionItem[]>>({});
  const [runRecordMap, setRunRecordMap] = useState<Record<string, ExperimentRunSummary[]>>({});
  const [selectedRunIdMap, setSelectedRunIdMap] = useState<Record<string, string>>({});
  const databaseQuestionCount = Object.values(questionSuiteMap).reduce((total, suite) => total + suite.questionCount, 0) || experimentQuestionCount;
  const controlTimerMap = useRef<Record<string, number>>({});

  useEffect(() => {
    if (evaluationPrompt) return;
    fetchTemplatePrompts()
      .then((items) => {
        savePromptCache(items);
        setEvaluationPrompt(items.find((item) => item.prompt_key === 'evaluate_prompt')?.prompt_text || '');
      })
      .catch(() => {
        setEvaluationPrompt('暂无评价标准。');
      });
  }, [evaluationPrompt]);

  useEffect(() => () => {
    Object.values(controlTimerMap.current).forEach((timerId) => window.clearInterval(timerId));
  }, []);

  useEffect(() => {
    experimentPlans.forEach((plan) => {
      void refreshExperimentRuns(plan.id);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    experimentPlans
      .filter((plan) => plan.questionSuiteId)
      .forEach((plan) => {
        const suiteId = plan.questionSuiteId as string;
        fetchExperimentQuestionSuite(suiteId)
          .then((suite) => {
            if (cancelled) return;
            setQuestionSuiteMap((prev) => ({ ...prev, [plan.id]: suite }));
            setSampledQuestionMap((prev) => ({
              ...prev,
              [plan.id]: pickRandomQuestionItems(getSuiteQuestionItems(suite), 3)
            }));
          })
          .catch((error) => {
            if (cancelled) return;
            setQuestionSuiteErrorMap((prev) => ({
              ...prev,
              [plan.id]: error instanceof Error ? error.message : '题库加载失败'
            }));
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const getControlState = (planId: string) => controlStateMap[planId] || defaultControlState;

  const getPlanInputs = (plan: ExperimentPlan) => sampledQuestionMap[plan.id]?.length ? sampledQuestionMap[plan.id].map((item) => item.questionText) : plan.inputs;

  const getPlanQuestionItems = (plan: ExperimentPlan): ExperimentQuestionItem[] => {
    const suiteItems = getSuiteQuestionItems(questionSuiteMap[plan.id]);
    if (suiteItems.length) return suiteItems;
    return plan.inputs.map((questionText) => ({ questionText }));
  };

  const getPlanEvaluationPrompt = (plan: ExperimentPlan) => {
    if (plan.questionSuiteId) return questionSuiteMap[plan.id]?.evaluationPrompt || '';
    return evaluationPrompt;
  };

  const getPlanEvaluationPromptSource = (plan: ExperimentPlan) => {
    if (plan.questionSuiteId) {
      if (questionSuiteMap[plan.id]?.evaluationPrompt) return '数据库专属提示词';
      if (questionSuiteErrorMap[plan.id]) return '专属提示词加载失败';
      return '专属提示词加载中';
    }
    return '通用评估提示词';
  };

  const refreshExperimentRuns = async (planId: string) => {
    try {
      const runs = await fetchExperimentRuns(planId);
      setRunRecordMap((prev) => ({ ...prev, [planId]: runs }));
    } catch {
      setRunRecordMap((prev) => ({ ...prev, [planId]: prev[planId] || [] }));
    }
  };

  const loadExperimentRun = async (plan: ExperimentPlan) => {
    const runId = selectedRunIdMap[plan.id];
    if (!runId) return;
    const detail = await fetchExperimentRunDetail(plan.id, runId);
    setOutputStateMap((prev) => ({ ...prev, [plan.id]: detail.outputState as ExperimentOutputState }));
    setEvaluationStateMap((prev) => ({ ...prev, [plan.id]: (detail.evaluationState as ExperimentEvaluationState) || defaultEvaluationState }));
    setControlStateMap((prev) => ({
      ...prev,
      [plan.id]: {
        ...(prev[plan.id] || defaultControlState),
        runCount: detail.run.runCount || defaultControlState.runCount,
        concurrency: Math.min(detail.run.concurrency || defaultControlState.concurrency, getMaxExperimentConcurrency(detail.run.runCount || defaultControlState.runCount, plan.processGroups.length)),
        generation: { status: detail.run.status === 'done' ? 'done' : 'idle', progress: detail.run.totalGroups ? Math.round((detail.run.completedGroups / detail.run.totalGroups) * 100) : 0 },
        evaluation: detail.evaluationState
          ? { status: detail.evaluationState.status === 'done' ? 'done' : detail.evaluationState.status === 'error' ? 'error' : 'idle', progress: Number(detail.evaluationState.progress || 0), message: detail.evaluationState.message }
          : defaultStageState
      }
    }));
  };

  const updateControlConfig = (planId: string, patch: Partial<Pick<ExperimentControlState, 'runCount' | 'concurrency' | 'evaluationConcurrency'>>) => {
    const groupCount = experimentPlans.find((plan) => plan.id === planId)?.processGroups.length || 1;
    setControlStateMap((prev) => ({
      ...prev,
      [planId]: (() => {
        const next = {
          ...defaultControlState,
          ...(prev[planId] || {}),
          ...patch
        };
        const maxConcurrency = getMaxExperimentConcurrency(next.runCount, groupCount);
        return {
          ...next,
          runCount: Math.max(next.runCount, 1),
          concurrency: Math.min(Math.max(next.concurrency, 1), maxConcurrency),
          evaluationConcurrency: Math.min(Math.max(next.evaluationConcurrency, 1), getMaxEvaluationConcurrency())
        };
      })()
    }));
  };

  const updateOutputState = (planId: string, updater: (current: ExperimentOutputState) => ExperimentOutputState) => {
    setOutputStateMap((prev) => ({
      ...prev,
      [planId]: updater(prev[planId] || defaultOutputState)
    }));
  };

  const updateEvaluationState = (planId: string, updater: (current: ExperimentEvaluationState) => ExperimentEvaluationState) => {
    setEvaluationStateMap((prev) => ({
      ...prev,
      [planId]: updater(prev[planId] || defaultEvaluationState)
    }));
  };

  const runEvaluationStage = async (plan: ExperimentPlan) => {
    const planId = plan.id;
    const selectedRunId = selectedRunIdMap[planId];
    const failEvaluation = (message: string) => {
      const errorState = { ...(evaluationStateMap[planId] || defaultEvaluationState), status: 'error' as const, progress: 0, message };
      setControlStateMap((prev) => ({
        ...prev,
        [planId]: {
          ...(prev[planId] || defaultControlState),
          evaluation: { status: 'error', progress: 0, message }
        }
      }));
      setEvaluationStateMap((prev) => ({
        ...prev,
        [planId]: errorState
      }));
      if (selectedRunId) void saveExperimentEvaluation(planId, selectedRunId, errorState).catch(() => {});
    };

    if (!selectedRunId) {
      failEvaluation('请先选择一次实验结果。');
      return;
    }
    let outputState = outputStateMap[planId] || defaultOutputState;
    if (!Object.keys(outputState.rounds).length) {
      try {
        const detail = await fetchExperimentRunDetail(planId, selectedRunId);
        outputState = detail.outputState as ExperimentOutputState;
        setOutputStateMap((prev) => ({ ...prev, [planId]: outputState }));
        if (detail.evaluationState) {
          setEvaluationStateMap((prev) => ({ ...prev, [planId]: detail.evaluationState as ExperimentEvaluationState }));
        }
        setControlStateMap((prev) => ({
          ...prev,
          [planId]: {
            ...(prev[planId] || defaultControlState),
            runCount: detail.run.runCount || defaultControlState.runCount,
            concurrency: Math.min(detail.run.concurrency || defaultControlState.concurrency, getMaxExperimentConcurrency(detail.run.runCount || defaultControlState.runCount, plan.processGroups.length)),
            generation: { status: detail.run.status === 'done' ? 'done' : 'idle', progress: detail.run.totalGroups ? Math.round((detail.run.completedGroups / detail.run.totalGroups) * 100) : 0 }
          }
        }));
      } catch (error) {
        failEvaluation(error instanceof Error ? error.message : '实验结果载入失败。');
        return;
      }
    }
    const tasks: ExperimentEvaluationTask[] = Object.entries(outputState.rounds).flatMap(([round, groupMap]) =>
      plan.processGroups.map((group) => ({
        round: Number(round),
        group,
        output: groupMap[group.id]
      })).filter((item): item is ExperimentEvaluationTask => Boolean(item.round && item.output?.outputText))
    );

    if (!tasks.length) {
      failEvaluation('暂无可评估的生成结果。');
      return;
    }

    const planEvaluationPrompt = getPlanEvaluationPrompt(plan);
    if (!planEvaluationPrompt) {
      failEvaluation(questionSuiteErrorMap[planId] || '本实验专属评估提示词尚未加载。');
      return;
    }

    setControlStateMap((prev) => ({
      ...prev,
      [planId]: {
        ...(prev[planId] || defaultControlState),
        evaluation: { status: 'running', progress: 0 }
      }
    }));
    setEvaluationStateMap((prev) => ({
      ...prev,
      [planId]: { status: 'running', progress: 0, scores: {} }
    }));

    const evaluationConcurrency = Math.min(getControlState(planId).evaluationConcurrency || 1, getMaxEvaluationConcurrency(), tasks.length);
    let savedScores: ExperimentEvaluationState['scores'] = {};
    let nextTaskIndex = 0;
    let completed = 0;

    const setSavedScore = (task: ExperimentEvaluationTask, score: ExperimentEvaluationScore) => {
      const roundKey = String(task.round);
      savedScores = {
        ...savedScores,
        [roundKey]: {
          ...(savedScores[roundKey] || {}),
          [task.group.id]: score
        }
      };
    };

    const persistEvaluation = (status: ExperimentEvaluationState['status'], progress: number, message?: string) => {
      const state = { status, progress, scores: savedScores, message };
      void saveExperimentEvaluation(planId, selectedRunId, state).then(() => refreshExperimentRuns(planId)).catch(() => {});
    };

    persistEvaluation('running', 0);

    const runWorker = async () => {
      while (nextTaskIndex < tasks.length) {
        const task = tasks[nextTaskIndex];
        nextTaskIndex += 1;
      const groupTitle = splitGroupName(task.group);
      updateEvaluationState(planId, (current) => ({
        ...current,
        status: 'running',
        current: { round: task.round, groupId: task.group.id, groupLabel: groupTitle.label },
        scores: {
          ...current.scores,
          [String(task.round)]: {
            ...(current.scores[String(task.round)] || {}),
            [task.group.id]: { groupId: task.group.id, groupLabel: groupTitle.label, status: 'running' }
          }
        }
      }));

      try {
        const result = await runEvaluationRequest(planEvaluationPrompt, task.output.outputText, {
          question: task.output.question || outputState.roundQuestions[String(task.round)] || '',
          questionGroup: questionItemLabel(task.output.questionItem || outputState.roundQuestionItems?.[String(task.round)]),
          groupLabel: groupTitle.label,
          groupTitle: groupTitle.title,
          round: task.round
        }, (patch) => {
          updateEvaluationState(planId, (current) => ({
            ...current,
            scores: {
              ...current.scores,
              [String(task.round)]: {
                ...(current.scores[String(task.round)] || {}),
                [task.group.id]: {
                  ...(current.scores[String(task.round)]?.[task.group.id] || {}),
                  groupId: task.group.id,
                  groupLabel: groupTitle.label,
                  status: 'running',
                  ...patch
                }
              }
            }
          }));
        });
        const doneScore: ExperimentEvaluationScore = {
          groupId: task.group.id,
          groupLabel: groupTitle.label,
          status: 'done',
          score: result.score,
          comment: result.comment,
          structuredEvaluation: result.structuredEvaluation,
          structuredError: result.structuredError
        };
        setSavedScore(task, doneScore);
        updateEvaluationState(planId, (current) => ({
          ...current,
          scores: {
            ...current.scores,
            [String(task.round)]: {
              ...(current.scores[String(task.round)] || {}),
              [task.group.id]: doneScore
            }
          }
        }));
      } catch (error) {
        const errorScore: ExperimentEvaluationScore = {
          groupId: task.group.id,
          groupLabel: groupTitle.label,
          status: 'error',
          comment: error instanceof Error ? error.message : '评估失败'
        };
        setSavedScore(task, errorScore);
        updateEvaluationState(planId, (current) => ({
          ...current,
          scores: {
            ...current.scores,
            [String(task.round)]: {
              ...(current.scores[String(task.round)] || {}),
              [task.group.id]: errorScore
            }
          }
        }));
      }

      completed += 1;
      const progress = Math.round((completed / tasks.length) * 100);
      setControlStateMap((prev) => ({
        ...prev,
        [planId]: {
          ...(prev[planId] || defaultControlState),
          evaluation: { status: progress >= 100 ? 'done' : 'running', progress }
        }
      }));
      updateEvaluationState(planId, (current) => ({
        ...current,
        status: progress >= 100 ? 'done' : 'running',
        progress,
        current: progress >= 100 ? undefined : current.current
      }));
      persistEvaluation(progress >= 100 ? 'done' : 'running', progress);
    }
    };

    await Promise.all(Array.from({ length: evaluationConcurrency }, () => runWorker()));
  };

  const runControlStage = async (plan: ExperimentPlan, stage: ExperimentControlStage, options: { runId?: string } = {}) => {
    const planId = plan.id;
    if (stage === 'evaluation') {
      await runEvaluationStage(plan);
      return;
    }
    const timerKey = `${planId}:${stage}`;
    if (controlTimerMap.current[timerKey]) {
      window.clearInterval(controlTimerMap.current[timerKey]);
      delete controlTimerMap.current[timerKey];
    }
    setControlStateMap((prev) => ({
      ...prev,
      [planId]: {
        ...defaultControlState,
        ...(prev[planId] || {}),
        [stage]: { status: 'running', progress: 0 }
      }
    }));

    const currentControl = getControlState(planId);
    const effectiveConcurrency = Math.min(currentControl.concurrency, getMaxExperimentConcurrency(currentControl.runCount, plan.processGroups.length));
    if (stage === 'generation' && !options.runId) {
      setOutputStateMap((prev) => ({ ...prev, [planId]: defaultOutputState }));
    }

    try {
      await streamExperimentRun(
        {
          planId,
          stage,
          runCount: currentControl.runCount,
          concurrency: effectiveConcurrency,
          questions: getPlanInputs(plan),
          questionItems: getPlanQuestionItems(plan),
          runId: options.runId
        },
        (eventName, data) => {
          if (data?.runId) {
            setSelectedRunIdMap((prev) => ({ ...prev, [planId]: String(data.runId) }));
          }

          if (eventName === 'experiment_stage_started' && data?.outputState) {
            setOutputStateMap((prev) => ({ ...prev, [planId]: data.outputState as ExperimentOutputState }));
            return;
          }

          if (eventName === 'experiment_stage_done') {
            if (data?.outputState) {
              setOutputStateMap((prev) => ({ ...prev, [planId]: data.outputState as ExperimentOutputState }));
            }
            void refreshExperimentRuns(planId);
            setControlStateMap((prev) => ({
              ...prev,
              [planId]: {
                ...(prev[planId] || defaultControlState),
                [stage]: { status: 'done', progress: 100 }
              }
            }));
            return;
          }

          if (eventName === 'experiment_progress') {
            const completed = Number(data?.completed || 0);
            const groupCount = plan.processGroups.length;
            const activeRound = groupCount > 0 ? Math.min(currentControl.runCount, Math.max(1, Math.ceil((completed + 1) / groupCount))) : undefined;
            setControlStateMap((prev) => ({
              ...prev,
              [planId]: {
                ...(prev[planId] || defaultControlState),
                [stage]: { status: data?.progress >= 100 ? 'done' : 'running', progress: Number(data?.progress || 0) }
              }
            }));
            updateOutputState(planId, (current) => ({ ...current, activeRound }));
            return;
          }

          if (eventName === 'experiment_round_started') {
            const round = Number(data.round || 0);
            if (!round) return;
            const questionItem = eventQuestionItem(data);
            updateOutputState(planId, (current) => ({
              ...current,
              activeRound: round,
              roundQuestions: {
                ...current.roundQuestions,
                [String(round)]: String(data.question || '')
              },
              roundQuestionItems: mergeRoundQuestionItem(current, String(round), questionItem)
            }));
            return;
          }

          if (eventName === 'experiment_group_started') {
            const round = Number(data.round || 0);
            const groupId = String(data.groupId || '');
            if (!round || !groupId) return;
            const questionItem = eventQuestionItem(data);
            updateOutputState(planId, (current) => ({
              ...current,
              activeGroups: addActiveGroup(current, { round, groupId, groupLabel: String(data.groupLabel || '') }),
              current: { round, groupId, groupLabel: String(data.groupLabel || '') },
              rounds: {
                ...current.rounds,
                [String(round)]: {
                  ...(current.rounds[String(round)] || {}),
                  [groupId]: {
                    groupId,
                    groupLabel: String(data.groupLabel || ''),
                    question: String(data.question || ''),
                    questionItem,
                    outputText: '',
                    streamingText: '',
                    status: 'running'
                  }
                }
              },
              roundQuestions: {
                ...current.roundQuestions,
                [String(round)]: String(data.question || current.roundQuestions[String(round)] || '')
              },
              roundQuestionItems: mergeRoundQuestionItem(current, String(round), questionItem)
            }));
            return;
          }

          if (eventName === 'experiment_group_chunk') {
            const round = Number(data.round || 0);
            const groupId = String(data.groupId || '');
            if (!round || !groupId) return;
            updateOutputState(planId, (current) => {
              const roundKey = String(round);
              const existing = current.rounds[roundKey]?.[groupId];
              if (!existing) return current;
              return {
                ...current,
                activeGroups: addActiveGroup(current, { round, groupId, groupLabel: existing.groupLabel }),
                current: { round, groupId, groupLabel: existing.groupLabel },
                rounds: {
                  ...current.rounds,
                  [roundKey]: {
                    ...current.rounds[roundKey],
                    [groupId]: {
                      ...existing,
                      streamingText: `${existing.streamingText}${String(data.text || '')}`,
                      status: 'running'
                    }
                  }
                },
                roundQuestions: {
                  ...current.roundQuestions,
                  [roundKey]: String(data.question || existing?.question || current.roundQuestions[roundKey] || '')
                },
                roundQuestionItems: mergeRoundQuestionItem(current, roundKey, existing?.questionItem || current.roundQuestionItems?.[roundKey])
              };
            });
            return;
          }

          if (eventName === 'experiment_group_done') {
            const round = Number(data.round || 0);
            const groupId = String(data.groupId || '');
            if (!round || !groupId) return;
            const questionItem = eventQuestionItem(data);
            updateOutputState(planId, (current) => {
              const roundKey = String(round);
              const existing = current.rounds[roundKey]?.[groupId];
              return {
                ...current,
                activeGroups: removeActiveGroup(current, round, groupId),
                current: { round, groupId, groupLabel: String(data.groupLabel || existing?.groupLabel || '') },
                rounds: {
                  ...current.rounds,
                  [roundKey]: {
                    ...(current.rounds[roundKey] || {}),
                    [groupId]: {
                      groupId,
                      groupLabel: String(data.groupLabel || existing?.groupLabel || ''),
                      question: String(data.question || existing?.question || ''),
                      questionItem: questionItem || existing?.questionItem,
                      outputText: String(data.outputText || ''),
                      streamingText: existing?.streamingText || '',
                      status: data?.status === 'terminated' ? 'terminated' : 'done'
                    }
                  }
                },
                roundQuestions: {
                  ...current.roundQuestions,
                  [roundKey]: String(existing?.question || current.roundQuestions[roundKey] || '')
                },
                roundQuestionItems: mergeRoundQuestionItem(current, roundKey, questionItem || existing?.questionItem || current.roundQuestionItems?.[roundKey])
              };
            });
            return;
          }

          if (eventName === 'experiment_group_error') {
            const round = Number(data.round || 0);
            const groupId = String(data.groupId || '');
            if (!round || !groupId) return;
            updateOutputState(planId, (current) => {
              const roundKey = String(round);
              const existing = current.rounds[roundKey]?.[groupId];
              return {
                ...current,
                activeGroups: removeActiveGroup(current, round, groupId),
                current: { round, groupId, groupLabel: existing?.groupLabel || groupId },
                rounds: {
                  ...current.rounds,
                  [roundKey]: {
                    ...(current.rounds[roundKey] || {}),
                    [groupId]: {
                      groupId,
                      groupLabel: existing?.groupLabel || groupId,
                      question: existing?.question || '',
                      outputText: String(data.message || '实验组执行失败'),
                      streamingText: existing?.streamingText || '',
                      status: 'error'
                    }
                  }
                }
              };
            });
          }
        }
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : '实验执行失败';
      updateOutputState(planId, (current) => ({ ...current, activeGroups: [] }));
      setControlStateMap((prev) => ({
        ...prev,
        [planId]: {
          ...(prev[planId] || defaultControlState),
          [stage]: { status: 'error', progress: 0, message }
        }
      }));
    }
  };

  return (
    <div className="experiment-page">
      <Card className="panel-card experiment-hero-card">
        <div className="experiment-hero-card__intro">
          <Space direction="vertical" size={12}>
            <Tag color="purple" className="experiment-hero-card__tag">
              <ExperimentOutlined /> 完整工作流实验接入点
            </Tag>
            <Title level={3} className="experiment-hero-card__title">对比实验</Title>
            <Paragraph className="experiment-hero-card__desc">
              基于现有示例题集和已接入插件，后续可在这里批量运行消融实验、压力测试和效率测试，集中展示当前工作流在边界拦截、主体消歧、图谱增强、模板结构和多故障处理上的优势。
            </Paragraph>
            <Space wrap>
              <Tag color="blue">单故障题 {ALL_SINGLE_FAULT_QUESTIONS.length} 条</Tag>
              <Tag color="red">多故障题 {ALL_MULTI_FAULT_QUESTIONS.length} 条</Tag>
              <Tag color="geekblue">数据库实验题 {databaseQuestionCount} 条</Tag>
              <Tag color="green">复用现有 FastGPT 插件</Tag>
            </Space>
          </Space>
          <Button type="primary" icon={<PlayCircleOutlined />} disabled>
            批量运行实验
          </Button>
        </div>
        <div className="experiment-hero-card__standard">
          <div className="experiment-hero-card__standard-header">
            <Text strong>当前评价标准</Text>
            <Tag color="cyan">评估提示词</Tag>
          </div>
          <Paragraph className="experiment-hero-card__standard-text">
            {evaluationPrompt || '正在加载评价标准...'}
          </Paragraph>
        </div>
      </Card>

      <div className="experiment-plan-list">
        {experimentPlans.map((plan) => {
          const cardView = cardViewMap[plan.id] || 'info';
          const planInputs = getPlanInputs(plan);
          const questionSuite = questionSuiteMap[plan.id];
          const questionSuiteError = questionSuiteErrorMap[plan.id];
          return (
          <Card
            className="panel-card experiment-plan-card"
            title={plan.title}
            extra={
              <Segmented
                size="small"
                value={cardView}
                options={[
                  { label: '实验信息', value: 'info' },
                  { label: '实验控制', value: 'control' },
                  { label: '产出预览', value: 'preview' },
                  { label: '评估结果', value: 'evaluation' }
                ]}
                onChange={(value) => setCardViewMap((prev) => ({ ...prev, [plan.id]: value as ExperimentCardView }))}
              />
            }
            key={plan.title}
          >
            {cardView === 'info' ? (
            <div className="experiment-plan-card__grid">
              <div className="experiment-plan-card__top-row">
                <ExperimentSection title="实验目的">
                  <Paragraph className="experiment-plan-card__text">{plan.objective}</Paragraph>
                </ExperimentSection>
                <ExperimentSection title="预期输出">
                  <ol className="experiment-plan-card__list">
                    {plan.expectedOutput.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ol>
                </ExperimentSection>
              </div>
              <ExperimentSection title="实验输入与特征" wide>
                <div className="experiment-plan-card__input-row">
                  <div className="experiment-plan-card__input-desc-wrap">
                    <Paragraph className="experiment-plan-card__input-desc">{plan.expectedInput}</Paragraph>
                    {plan.questionSuiteId ? (
                      <div className="experiment-plan-card__suite-actions">
                        <Tag color={questionSuite ? 'geekblue' : questionSuiteError ? 'red' : 'processing'}>
                          {questionSuite ? `数据库题库 ${questionSuite.questionCount} 条` : questionSuiteError ? '题库加载失败' : '题库加载中'}
                        </Tag>
                        <Popover
                          content={questionSuite ? <ExperimentQuestionPopover suite={questionSuite} /> : <div className="experiment-plan-card__suite-empty">{questionSuiteError || '正在加载题库...'}</div>}
                          trigger="click"
                          placement="bottomLeft"
                          destroyTooltipOnHide
                          overlayClassName="preset-popover"
                        >
                          <Button size="small" disabled={!questionSuite && !questionSuiteError}>查看全部问题</Button>
                        </Popover>
                      </div>
                    ) : null}
                  </div>
                  <div className="experiment-plan-card__examples">
                    {planInputs.map((input) => (
                      <div className="experiment-plan-card__example" key={input}>{input}</div>
                    ))}
                  </div>
                </div>
              </ExperimentSection>
              <ExperimentSection title="实验过程" wide>
                <div className="experiment-plan-card__groups">
                  {plan.processGroups.map((group) => (
                    <div className={`experiment-plan-card__group is-${group.role === '对照组' ? 'control' : 'experiment'}`} key={group.id}>
                      <div className="experiment-plan-card__group-header">
                        <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{splitGroupName(group).label}</Tag>
                        <Text strong>{splitGroupName(group).title}</Text>
                      </div>
                      <Paragraph className="experiment-plan-card__text">{group.summary}</Paragraph>
                      <ExperimentFlowDiagram planId={plan.id} group={group} showStatus={false} />
                    </div>
                  ))}
                </div>
              </ExperimentSection>
            </div>
            ) : (
              cardView === 'control' ? (
              <ExperimentControlPanel
                plan={plan}
                state={getControlState(plan.id)}
                runs={runRecordMap[plan.id] || []}
                selectedRunId={selectedRunIdMap[plan.id]}
                outputState={outputStateMap[plan.id] || defaultOutputState}
                onUpdateConfig={(patch) => updateControlConfig(plan.id, patch)}
                onRunStage={(stage, options) => void runControlStage(plan, stage, options)}
                onSelectRun={(runId) => setSelectedRunIdMap((prev) => ({ ...prev, [plan.id]: runId }))}
                onLoadRun={() => void loadExperimentRun(plan)}
                onRefreshRuns={() => void refreshExperimentRuns(plan.id)}
              />
              ) : (
                cardView === 'preview' ? (
                  <ExperimentOutputPreview
                    plan={plan}
                    outputState={outputStateMap[plan.id] || defaultOutputState}
                    runs={runRecordMap[plan.id] || []}
                    selectedRunId={selectedRunIdMap[plan.id]}
                    onSelectRun={(runId) => setSelectedRunIdMap((prev) => ({ ...prev, [plan.id]: runId }))}
                    onLoadRun={() => void loadExperimentRun(plan)}
                    onRefreshRuns={() => void refreshExperimentRuns(plan.id)}
                  />
                ) : (
                  <ExperimentEvaluationPanel
                    plan={plan}
                    evaluationPrompt={getPlanEvaluationPrompt(plan)}
                    promptSource={getPlanEvaluationPromptSource(plan)}
                    evaluationState={evaluationStateMap[plan.id] || defaultEvaluationState}
                    runs={runRecordMap[plan.id] || []}
                    selectedRunId={selectedRunIdMap[plan.id]}
                    evaluationRunning={getControlState(plan.id).evaluation.status === 'running'}
                    evaluationConcurrency={getControlState(plan.id).evaluationConcurrency}
                    onUpdateEvaluationConcurrency={(value) => updateControlConfig(plan.id, { evaluationConcurrency: value })}
                    onSelectRun={(runId) => setSelectedRunIdMap((prev) => ({ ...prev, [plan.id]: runId }))}
                    onLoadRun={() => void loadExperimentRun(plan)}
                    onRefreshRuns={() => void refreshExperimentRuns(plan.id)}
                    onRunEvaluation={() => void runControlStage(plan, 'evaluation')}
                  />
                )
              )
            )}
          </Card>
          );
        })}
      </div>
    </div>
  );
}
