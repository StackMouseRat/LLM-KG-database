import { Button, Card, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ALL_MULTI_FAULT_QUESTIONS, ALL_SINGLE_FAULT_QUESTIONS, EXPERIMENT_QUESTION_GROUPS } from '../data/presetQuestions';

const { Paragraph, Text, Title } = Typography;

type ExperimentStepStatus = 'pending' | 'running' | 'done' | 'failed';

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
  variables?: string[];
  connectsToNext?: boolean;
};

type ExperimentProcessGroup = {
  id: string;
  role: '对照组' | '实验组';
  name: string;
  summary: string;
  nodes: ExperimentFlowNode[];
};

type ExperimentPlan = {
  id: string;
  title: string;
  tag: string;
  objective: string;
  processGroups: ExperimentProcessGroup[];
  inputs: string[];
  expectedInput: string;
  expectedOutput: string[];
  metrics: string[];
};

type VariableConnection = {
  id: string;
  path: string;
};

const experimentStepStatusText: Record<ExperimentStepStatus, string> = {
  pending: '待运行',
  running: '进行中',
  done: '已完成',
  failed: '异常'
};

const node = (plugin: string, input: string, output: string, variables: string[] = [], connectsToNext = true): ExperimentFlowNode => ({
  plugin,
  input,
  output,
  variables,
  connectsToNext
});

const completeWorkflowNodes = [
  node('基本信息获取', '用户问题', 'reason、故障类型分析、知识库名、图谱检索方案素材、模板文本', ['保留：边界校验 reason/message', '保留：图谱检索方案素材']),
  node('知识库案例检索', '用户问题 + 故障类型分析 + 知识库名', '相似案例卡片', ['保留：案例增强素材']),
  node('模板切片', '模板文本 + 故障场景', '章节列表、章节标题、章节模板文本', ['保留：章节边界约束']),
  node('并行生成', '用户问题 + 故障场景 + 图谱素材 + 案例素材 + 章节模板', '分章节预案正文', ['保留：完整上下文输入'])
];

const completeWorkflowGroup: ExperimentProcessGroup = {
  id: 'control',
  role: '对照组',
  name: '本项目完整流程',
  summary: '保留当前项目的完整链路，作为所有实验的统一对照基线。',
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

const variableAlias: Record<string, string> = {
  图谱素材: '图谱检索方案素材',
  原因现象图谱素材: '图谱检索方案素材',
  完整图谱检索方案素材: '图谱检索方案素材',
  主故障图谱检索方案素材: '图谱检索方案素材',
  章节模板: '章节模板文本',
  章节模板文本: '章节模板文本',
  章节列表: '章节列表',
  故障场景: '故障类型分析',
  单一故障场景: '故障类型分析',
  多故障场景: '故障类型分析',
  去约束故障场景: '故障类型分析',
  案例素材: '相似案例卡片',
  相似案例卡片: '相似案例卡片',
  用户问题: '用户问题',
  原始题目: '用户问题',
  混淆类用户问题: '用户问题',
  图谱依赖类用户问题: '用户问题',
  正式预案生成需求: '用户问题',
  多故障用户问题: '用户问题',
  带约束用户问题: '用户问题'
};

function getVariableTags(value: string) {
  return value
    .split(/\s*[+、，,]\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function canonicalVariable(value: string) {
  const normalized = value.replace(/=.*$/, '').trim();
  return variableAlias[normalized] || normalized;
}

function getSharedVariables(currentNode: ExperimentFlowNode, nextNode: ExperimentFlowNode | undefined) {
  if (!nextNode) return [];
  const nextInputs = new Set(getVariableTags(nextNode.input).map(canonicalVariable));
  return getVariableTags(currentNode.output).filter((variable) => nextInputs.has(canonicalVariable(variable)));
}

function orderVariablesByReference(variables: string[], referenceVariables: string[]) {
  const referenceOrder = new Map(referenceVariables.map((variable, index) => [canonicalVariable(variable), index]));
  return variables
    .map((variable, originalIndex) => ({
      variable,
      originalIndex,
      referenceIndex: referenceOrder.get(canonicalVariable(variable))
    }))
    .sort((left, right) => {
      const leftConnected = left.referenceIndex !== undefined;
      const rightConnected = right.referenceIndex !== undefined;
      if (leftConnected !== rightConnected) return leftConnected ? -1 : 1;
      if (leftConnected && rightConnected && left.referenceIndex !== right.referenceIndex) {
        return Number(left.referenceIndex) - Number(right.referenceIndex);
      }
      return left.originalIndex - right.originalIndex;
    })
    .map((item) => item.variable);
}

function getConnectionOrder(currentNode: ExperimentFlowNode | undefined, nextNode: ExperimentFlowNode | undefined) {
  if (!currentNode || !nextNode) return [];
  const nextInputKeys = new Set(getVariableTags(nextNode.input).map(canonicalVariable));
  return getVariableTags(currentNode.output).filter((variable) => nextInputKeys.has(canonicalVariable(variable)));
}

function getOrderedInputVariables(group: ExperimentProcessGroup, nodeIndex: number) {
  const variables = getVariableTags(group.nodes[nodeIndex].input);
  const previousNode = group.nodes[nodeIndex - 1];
  return previousNode ? orderVariablesByReference(variables, getConnectionOrder(previousNode, group.nodes[nodeIndex])) : variables;
}

function getOrderedOutputVariables(group: ExperimentProcessGroup, nodeIndex: number) {
  const variables = getVariableTags(group.nodes[nodeIndex].output);
  const nextNode = group.nodes[nodeIndex + 1];
  return nextNode ? orderVariablesByReference(variables, getConnectionOrder(group.nodes[nodeIndex], nextNode)) : variables;
}

function buildConnectionPath(x1: number, y1: number, x2: number, y2: number) {
  const midY = y1 + (y2 - y1) / 2;
  return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
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
        summary: '仍复用现有插件，但不使用基本信息获取插件输出的边界判断。',
        nodes: [
          node('基本信息获取', '用户问题', '故障类型分析、知识库名、图谱检索方案素材、模板文本', ['丢弃：reason/message']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '用户问题 + 故障场景 + 图谱素材 + 章节模板', '预案正文', ['无论 reason 是否异常都继续生成'])
        ]
      },
      {
        id: 'exp-keyword-boundary',
        role: '实验组',
        name: '实验组二：关键词边界校验',
        summary: '用关键词结果替换基本信息获取插件的边界判断，其余插件保持不变。',
        nodes: [
          node('基本信息获取', '用户问题 + 关键词预筛结果', '故障类型分析、知识库名、图谱检索方案素材', ['替换：reason = 关键词规则结果']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '关键词放行样本 + 图谱素材 + 章节模板', '预案正文', ['观察：关键词误放行导致的伪预案'])
        ]
      },
      {
        id: 'exp-boundary-no-stop',
        role: '实验组',
        name: '实验组三：校验但不终止',
        summary: '保留基本信息获取插件的 reason/message 输出，但不把异常结果用于阻断。',
        nodes: [
          node('基本信息获取', '用户问题', 'reason、message、故障类型分析、图谱检索方案素材', ['保留但不使用：reason/message']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '异常输入 + 图谱素材 + 章节模板', '预案正文', ['变量冲突：已识别异常但仍生成'])
        ]
      }
    ],
    inputs: ['今天吃什么？', '发电机转子接地故障，请生成应急方案。', '变压器拒动，请生成应急方案。'],
    expectedInput: '非电力问题、不支持设备问题、设备和动作明显不兼容的问题。',
    expectedOutput: ['异常输入应被终止并给出 reason/message。', '后续模板切片、图谱检索和章节生成不应启动。', '实验组用于观察误放行、伪预案和错误正文长度。'],
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
        id: 'exp-direct-generate',
        role: '实验组',
        name: '实验组一：直接生成',
        summary: '跳过主体识别输出，直接把原始题目送入模板和生成插件。',
        nodes: [
          node('模板切片', '默认模板文本 + 原始题目', '章节列表、章节模板文本', ['丢弃：故障类型分析、知识库名']),
          node('并行生成', '原始题目 + 章节模板', '预案正文', ['丢弃：图谱检索方案素材']),
          node('知识库案例检索', '原始题目', '相似案例卡片', ['弱化：设备主体约束'])
        ]
      },
      {
        id: 'exp-basic-info-only',
        role: '实验组',
        name: '实验组二：仅基本信息获取',
        summary: '保留主体识别结果，但不把图谱素材传入最终生成。',
        nodes: [
          node('基本信息获取', '混淆类用户问题', '故障类型分析、知识库名、图谱检索方案素材', ['保留：设备主体识别结果']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '故障场景 + 章节模板', '预案正文', ['丢弃：图谱检索方案素材'])
        ]
      },
      {
        id: 'exp-graph-without-disambiguation',
        role: '实验组',
        name: '实验组三：首个设备词检索',
        summary: '复用图谱结果生成，但故障主体按题面首个设备词固定。',
        nodes: [
          node('基本信息获取', '首个设备词 + 用户问题', '图谱检索方案素材', ['替换：设备主体 = 题面首个设备词']),
          node('模板切片', '模板文本 + 首个设备词故障场景', '章节列表、章节模板文本'),
          node('并行生成', '首个设备词图谱素材 + 章节模板', '预案正文', ['观察：知识库误命中'])
        ]
      }
    ],
    inputs: ['主变旁110kV断路器保护发令后无法分闸，请生成应急处置方案。', '开关柜内电流互感器二次开路，电流表指示接近零，请生成现场方案。', '线路侧避雷器雨后出现放电痕迹并损坏，请生成应急方案。'],
    expectedInput: '包含多个设备名或位置修饰词，但只有一个真实故障主体的问题。',
    expectedOutput: ['输出应围绕真正故障主体展开。', '知识库和故障二级节点应与主体一致。', '实验组用于观察主体漂移和知识库误命中。'],
    metrics: ['设备识别正确率', '知识库命中率', '故障二级节点准确率', '正文主体一致性']
  },
  {
    id: 'graph',
    title: '图谱增强实验',
    tag: '图谱',
    objective: '验证图谱检索素材能提升故障原因、现象、措施、风险和应急资源的事实覆盖度。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-no-graph',
        role: '实验组',
        name: '实验组一：不传图谱素材',
        summary: '复用基本信息、模板切片和并行生成插件，仅在生成输入中移除图谱素材。',
        nodes: [
          node('基本信息获取', '图谱依赖类用户问题', '故障类型分析、图谱检索方案素材、模板文本', ['生成前丢弃：图谱检索方案素材']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '故障场景 + 章节模板 + 图谱素材=知识图谱无数据', '预案正文', ['替换：图谱检索方案素材 = 知识图谱无数据'])
        ]
      },
      {
        id: 'exp-case-only',
        role: '实验组',
        name: '实验组二：仅案例增强',
        summary: '保留案例检索插件输出，用案例素材替代知识图谱事实链。',
        nodes: [
          node('基本信息获取', '用户问题', '故障类型分析、知识库名、图谱检索方案素材', ['丢弃：图谱检索方案素材']),
          node('知识库案例检索', '用户问题 + 故障类型分析 + 知识库名', '相似案例卡片', ['保留：案例素材']),
          node('并行生成', '故障场景 + 案例素材 + 章节模板', '预案正文', ['替换：图谱素材 -> 案例素材'])
        ]
      },
      {
        id: 'exp-partial-graph',
        role: '实验组',
        name: '实验组三：部分图谱增强',
        summary: '复用图谱检索结果，但只保留原因和现象字段。',
        nodes: [
          node('基本信息获取', '用户问题', '完整图谱检索方案素材', ['裁剪：仅保留原因、现象']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '原因现象图谱素材 + 章节模板', '预案正文', ['丢弃：措施、风险、资源字段'])
        ]
      }
    ],
    inputs: ['雨后某220kV避雷器出现放电痕迹并伴随泄漏电流异常升高，请生成应急处置方案。', '电缆接头附近温度持续升高，并有焦糊味，后台出现绝缘告警，请生成处置方案。', '断路器保护发令后未动作，现场未见分闸，请生成包含检查确认和抢修措施的方案。'],
    expectedInput: '需要图谱事实补充故障原因、现象、措施、后果、风险和资源的问题。',
    expectedOutput: ['对照组应覆盖图谱事实。', '无图谱组和部分图谱组应暴露事实缺口。', '案例组用于观察案例迁移是否带来错配。'],
    metrics: ['原因覆盖度', '措施覆盖度', '风险资源覆盖度', '泛化空话比例']
  },
  {
    id: 'template',
    title: '模板结构实验',
    tag: '模板',
    objective: '验证模板切片和并行章节生成能稳定产出符合预案库格式的完整结构。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-free-form',
        role: '实验组',
        name: '实验组一：自由生成整篇',
        summary: '跳过模板切片插件，不向生成插件传入章节模板。',
        nodes: [
          node('基本信息获取', '正式预案生成需求', '故障场景、图谱检索方案素材、模板文本', ['丢弃：模板文本']),
          node('并行生成', '用户问题 + 故障场景 + 图谱素材', '整篇预案正文', ['丢弃：章节模板文本']),
          node('知识库案例检索', '用户问题 + 故障场景', '相似案例卡片', ['作为正文补充，不约束章节'])
        ]
      },
      {
        id: 'exp-template-no-slice',
        role: '实验组',
        name: '实验组二：整模板单次生成',
        summary: '保留模板文本，但不使用模板切片插件拆分章节。',
        nodes: [
          node('基本信息获取', '用户问题', '故障场景、图谱检索方案素材、完整模板文本', ['保留：完整模板文本']),
          node('并行生成', '完整模板文本 + 图谱素材 + 故障场景', '整篇预案正文', ['替换：章节模板 -> 完整模板']),
          node('知识库案例检索', '用户问题 + 故障场景', '相似案例卡片', ['观察：长上下文下案例是否被忽略'])
        ]
      },
      {
        id: 'exp-slice-without-section-context',
        role: '实验组',
        name: '实验组三：切片但弱化章节约束',
        summary: '复用模板切片插件，但生成阶段不强调“只生成当前章节”。',
        nodes: [
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本', ['保留：章节列表']),
          node('基本信息获取', '用户问题', '故障场景、图谱检索方案素材'),
          node('并行生成', '故障场景 + 图谱素材 + 章节模板', '章节正文', ['弱化：章节边界约束'])
        ]
      }
    ],
    inputs: ['请针对某110kV断路器拒动故障生成一份可纳入预案库的正式文本。', '某电缆接头击穿起火，请生成包含响应终止和恢复验证的完整预案。', '某互感器二次开路，现场存在人身触电风险，请生成完整应急预案。'],
    expectedInput: '要求生成正式预案、完整预案或可纳入预案库文本的问题。',
    expectedOutput: ['输出应包含完整章节。', '章节编号和标题应与模板切片保持一致。', '实验组用于观察章节缺失、重复和串章。'],
    metrics: ['章节完整率', '标题一致性', '章节边界稳定性', '章节空缺率']
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
          node('多故障基本信息获取', '多故障用户问题', '故障列表、主故障、模板文本', ['保留：多个故障对象']),
          node('逐故障图谱检索', '故障列表', '逐故障图谱检索素材', ['保留：每个故障的图谱素材']),
          node('模板切片', '模板文本 + 多故障场景', '章节列表、章节模板文本'),
          node('并行生成', '多故障场景 + 逐故障图谱素材 + 章节模板', '融合后的预案正文', ['保留：主次故障融合'])
        ]
      },
      {
        id: 'exp-single-fault',
        role: '实验组',
        name: '实验组一：单故障普通链路',
        summary: '把多故障问题强制送入单故障插件链路。',
        nodes: [
          node('基本信息获取', '多故障用户问题', '单一故障场景、知识库名、图谱检索方案素材', ['丢弃：次生故障和伴随故障']),
          node('模板切片', '模板文本 + 单故障场景', '章节列表、章节模板文本'),
          node('并行生成', '单故障图谱素材 + 章节模板', '预案正文', ['变量固定：只保留主故障'])
        ]
      },
      {
        id: 'exp-detect-no-per-fault-graph',
        role: '实验组',
        name: '实验组二：识别多故障但不逐项检索',
        summary: '复用多故障基本信息获取插件，但不调用逐故障图谱检索插件。',
        nodes: [
          node('多故障基本信息获取', '多故障用户问题', '故障列表、主故障、模板文本', ['保留：故障列表']),
          node('基本信息获取', '主故障文本', '主故障图谱检索方案素材', ['替换：逐故障检索 -> 主故障检索']),
          node('并行生成', '故障列表 + 主故障图谱素材 + 章节模板', '预案正文', ['丢弃：次生故障图谱素材'])
        ]
      },
      {
        id: 'exp-per-fault-no-fusion',
        role: '实验组',
        name: '实验组三：逐故障检索但不融合排序',
        summary: '复用逐故障图谱检索插件，但生成阶段只拼接素材，不做主次融合。',
        nodes: [
          node('多故障基本信息获取', '多故障用户问题', '故障列表、主故障、模板文本'),
          node('逐故障图谱检索', '故障列表', '逐故障图谱检索素材', ['保留：逐故障素材']),
          node('并行生成', '简单拼接的逐故障素材 + 章节模板', '预案正文', ['丢弃：主次排序和融合约束'])
        ]
      }
    ],
    inputs: ['吊车碰线后线路跳闸，通信光缆同时中断，保护通道异常，请生成处置预案。', '暴雨后电缆沟进水，电缆接头绝缘告警，同时环网柜出现凝露和局放异常，请生成应急方案。', '输电线路山火跳闸后，光缆通信中断，远方保护通道退出，请生成应急处置方案。'],
    expectedInput: '一个场景中出现多个设备、多个故障或先后诱发关系的问题。',
    expectedOutput: ['输出应识别多个故障。', '输出应区分主故障、伴随故障和受影响业务。', '实验组用于观察次生故障遗漏和素材拼接冲突。'],
    metrics: ['故障拆解率', '主次识别正确率', '逐故障图谱覆盖率', '融合处置完整度']
  },
  {
    id: 'constraints',
    title: '场景约束传播实验',
    tag: '约束',
    objective: '验证夜间、暴雨、不停电、保供、备件不到位、信息不全等约束能传递到最终正文。',
    processGroups: [
      completeWorkflowGroup,
      {
        id: 'exp-no-constraint',
        role: '实验组',
        name: '实验组一：不抽取场景约束',
        summary: '复用现有插件，但在插件间传递时移除场景约束。',
        nodes: [
          node('基本信息获取', '带约束用户问题', '故障场景、图谱检索方案素材、模板文本', ['丢弃：夜间/暴雨/保供/不停电约束']),
          node('模板切片', '模板文本 + 去约束故障场景', '章节列表、章节模板文本'),
          node('并行生成', '去约束故障场景 + 图谱素材 + 章节模板', '预案正文', ['观察：与约束冲突的措施'])
        ]
      },
      {
        id: 'exp-initial-constraint-only',
        role: '实验组',
        name: '实验组二：仅首轮注入约束',
        summary: '只在基本信息获取阶段保留约束，不在章节生成阶段重复传递。',
        nodes: [
          node('基本信息获取', '带约束用户问题', '故障场景、约束信息、图谱检索方案素材', ['保留：约束信息']),
          node('模板切片', '模板文本 + 故障场景', '章节列表、章节模板文本'),
          node('并行生成', '故障场景 + 图谱素材 + 章节模板', '预案正文', ['丢弃：章节生成阶段约束信息'])
        ]
      },
      {
        id: 'exp-constraint-no-conflict-check',
        role: '实验组',
        name: '实验组三：保留约束但不复核冲突',
        summary: '保留约束传递，但生成后不使用质量评估插件检查冲突措施。',
        nodes: [
          node('基本信息获取', '带约束用户问题', '故障场景、约束信息、图谱检索方案素材'),
          node('并行生成', '约束信息 + 图谱素材 + 章节模板', '预案正文', ['保留：约束信息']),
          node('格式优化与质量评估', '预案正文 + 约束背景', '格式优化文本与质量结论', ['丢弃：冲突措施复核结论'])
        ]
      }
    ],
    inputs: ['夜间暴雨中某电缆沟进水，电缆接头温度异常，用户要求不停电先控制风险，再视情况安排停电检修，请生成应急方案。', '某110kV断路器拒动，要求先保障重要负荷供电，再安排停电检修，请生成双阶段处置方案。', '某断路器合闸失败，但暂不清楚控制电源、储能状态和机构状态，请生成排查型方案。'],
    expectedInput: '包含时间、天气、保供、不停电、资源不足或信息不完整约束的问题。',
    expectedOutput: ['输出应体现阶段安排和约束传播。', '信息不全时应输出排查路径。', '实验组用于观察约束丢失和冲突措施。'],
    metrics: ['约束保留率', '排查路径完整度', '冲突措施避免率', '阶段安排清晰度']
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

function ExperimentFlowDiagram({ planId, group }: { planId: string; group: ExperimentProcessGroup }) {
  const flowRef = useRef<HTMLDivElement>(null);
  const [connections, setConnections] = useState<VariableConnection[]>([]);
  const [flowSize, setFlowSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const root = flowRef.current;
    if (!root) return undefined;

    const updateConnections = () => {
      const rootRect = root.getBoundingClientRect();
      const nextConnections: VariableConnection[] = [];

      group.nodes.forEach((flowNode, index) => {
        const nextNode = group.nodes[index + 1];
        if (!nextNode || flowNode.connectsToNext === false) return;

        const outputTags = Array.from(root.querySelectorAll<HTMLElement>(`[data-node-index="${index}"][data-variable-role="output"]`));
        const inputTags = Array.from(root.querySelectorAll<HTMLElement>(`[data-node-index="${index + 1}"][data-variable-role="input"]`));

        getSharedVariables(flowNode, nextNode).forEach((variable) => {
          const variableKey = canonicalVariable(variable);
          const outputTag = outputTags.find((tag) => tag.dataset.variableKey === variableKey);
          const inputTag = inputTags.find((tag) => tag.dataset.variableKey === variableKey);
          if (!outputTag || !inputTag) return;

          const outputRect = outputTag.getBoundingClientRect();
          const inputRect = inputTag.getBoundingClientRect();
          const x1 = outputRect.left + outputRect.width / 2 - rootRect.left;
          const y1 = outputRect.bottom - rootRect.top;
          const x2 = inputRect.left + inputRect.width / 2 - rootRect.left;
          const y2 = inputRect.top - rootRect.top;

          nextConnections.push({
            id: `${index}-${index + 1}-${variableKey}`,
            path: buildConnectionPath(x1, y1, x2, y2)
          });
        });
      });

      setFlowSize({ width: root.clientWidth, height: root.clientHeight });
      setConnections(nextConnections);
    };

    updateConnections();
    const animationFrame = requestAnimationFrame(updateConnections);
    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(updateConnections) : null;
    resizeObserver?.observe(root);
    root.querySelectorAll('.experiment-plan-card__var-tag').forEach((element) => resizeObserver?.observe(element));
    window.addEventListener('resize', updateConnections);

    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', updateConnections);
    };
  }, [group]);

  return (
    <div className="experiment-plan-card__flow" ref={flowRef}>
      {flowSize.width > 0 && flowSize.height > 0 ? (
        <svg className="experiment-plan-card__variable-lines" viewBox={`0 0 ${flowSize.width} ${flowSize.height}`} aria-hidden="true">
          {connections.map((connection) => (
            <path d={connection.path} key={connection.id} />
          ))}
        </svg>
      ) : null}
      {group.nodes.map((flowNode, index) => {
        const stepStatus = getExperimentStepStatus(experimentProgressByPlan[planId], group.id, index);
        const inputVariables = getOrderedInputVariables(group, index);
        const outputVariables = getOrderedOutputVariables(group, index);
        return (
          <div className="experiment-plan-card__flow-step" key={`${flowNode.plugin}-${index}`}>
            <div className={`experiment-plan-card__flow-node is-${stepStatus}`}>
              <div className="experiment-plan-card__boundary is-input">
                <Tag color="blue" className="experiment-plan-card__boundary-label">输入</Tag>
                <div className="experiment-plan-card__var-tags">
                  {inputVariables.map((variable) => (
                    <Tag
                      color="geekblue"
                      className="experiment-plan-card__var-tag"
                      data-node-index={index}
                      data-variable-key={canonicalVariable(variable)}
                      data-variable-role="input"
                      key={variable}
                    >
                      {variable}
                    </Tag>
                  ))}
                </div>
              </div>
              <span className="experiment-plan-card__flow-index">{index + 1}</span>
              <Text strong className="experiment-plan-card__plugin-title">{flowNode.plugin}</Text>
              <span className="experiment-plan-card__flow-status">{experimentStepStatusText[stepStatus]}</span>
              {flowNode.variables && flowNode.variables.length > 0 ? (
                <div className="experiment-plan-card__variables">
                  {flowNode.variables.map((variable) => (
                    <Tag color="volcano" key={variable}>{variable}</Tag>
                  ))}
                </div>
              ) : null}
              <div className="experiment-plan-card__boundary is-output">
                <Tag color="green" className="experiment-plan-card__boundary-label">输出</Tag>
                <div className="experiment-plan-card__var-tags">
                  {outputVariables.map((variable) => (
                    <Tag
                      color="green"
                      className="experiment-plan-card__var-tag"
                      data-node-index={index}
                      data-variable-key={canonicalVariable(variable)}
                      data-variable-role="output"
                      key={variable}
                    >
                      {variable}
                    </Tag>
                  ))}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ExperimentPage() {
  const experimentQuestionCount = EXPERIMENT_QUESTION_GROUPS.reduce((total, group) => total + group.questions.length, 0);

  return (
    <div className="experiment-page">
      <Card className="panel-card experiment-hero-card">
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
            <Tag color="geekblue">实验备用题 {experimentQuestionCount} 条</Tag>
            <Tag color="green">复用现有 FastGPT 插件</Tag>
          </Space>
        </Space>
        <Button type="primary" icon={<PlayCircleOutlined />} disabled>
          批量运行实验
        </Button>
      </Card>

      <div className="experiment-plan-list">
        {experimentPlans.map((plan) => (
          <Card className="panel-card experiment-plan-card" title={plan.title} extra={<Tag color="purple">{plan.tag}</Tag>} key={plan.title}>
            <div className="experiment-plan-card__grid">
              <ExperimentSection title="实验目的">
                <Paragraph className="experiment-plan-card__text">{plan.objective}</Paragraph>
              </ExperimentSection>
              <ExperimentSection title="实验过程" wide>
                <div className="experiment-plan-card__groups">
                  {plan.processGroups.map((group) => (
                    <div className={`experiment-plan-card__group is-${group.role === '对照组' ? 'control' : 'experiment'}`} key={group.id}>
                      <div className="experiment-plan-card__group-header">
                        <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{group.role}</Tag>
                        <Text strong>{group.name}</Text>
                      </div>
                      <Paragraph className="experiment-plan-card__text">{group.summary}</Paragraph>
                      <ExperimentFlowDiagram planId={plan.id} group={group} />
                    </div>
                  ))}
                </div>
              </ExperimentSection>
              <ExperimentSection title="实验输入与特征">
                <Paragraph className="experiment-plan-card__text">{plan.expectedInput}</Paragraph>
                <div className="experiment-plan-card__examples">
                  {plan.inputs.map((input) => (
                    <div className="experiment-plan-card__example" key={input}>{input}</div>
                  ))}
                </div>
              </ExperimentSection>
              <ExperimentSection title="预期输出">
                <ol className="experiment-plan-card__list">
                  {plan.expectedOutput.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </ExperimentSection>
              <ExperimentSection title="评价指标">
                <div className="experiment-plan-card__metrics">
                  {plan.metrics.map((metric) => (
                    <Tag key={metric}>{metric}</Tag>
                  ))}
                </div>
              </ExperimentSection>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
