import { Button, Card, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';
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
  node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '分章节预案正文', ['逐章并发调用并行生成插件'], '逐章并发')
];

const completeWorkflowGroup: ExperimentProcessGroup = {
  id: 'control',
  role: '对照组',
  name: '本项目完整流程',
  summary: '完整链路基线。',
  supportTags: ['图谱', '模板', '案例', '工作流'],
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
          node('基本信息获取', '用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['丢弃边界判定']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['无论 reason 是否异常都继续生成'], '逐章并发')
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
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['观察：关键词误放行导致的伪预案'], '逐章并发')
        ]
      },
    ],
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
        id: 'exp-direct-generate',
        role: '实验组',
        name: '实验组一：直接生成',
        summary: '原题直接生成。',
        supportTags: ['模板', '工作流'],
        nodes: [
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板', '丢弃：故障与场景提取结果、知识库名']),
          node('并行生成', '用户问题 + 章节模板文本', '预案正文', ['丢弃：图谱检索方案素材'], '逐章并发')
        ]
      },
      {
        id: 'exp-basic-info-only',
        role: '实验组',
        name: '实验组二：仅基本信息获取',
        summary: '保留主体，移除图谱。',
        supportTags: ['模板', '工作流'],
        nodes: [
          node('基本信息获取', '混淆类用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['保留：设备主体识别结果']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 章节模板文本', '预案正文', ['丢弃：图谱检索方案素材'], '逐章并发')
        ]
      },
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
        summary: '移除图谱素材。',
        supportTags: ['模板', '工作流'],
        nodes: [
          node('基本信息获取', '图谱依赖类用户问题', '故障与场景提取结果、图谱检索方案素材', ['生成前丢弃：图谱检索方案素材']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 章节模板文本 + 图谱检索方案素材=知识图谱无数据', '预案正文', ['替换：图谱检索方案素材 = 知识图谱无数据'], '逐章并发')
        ]
      },
      {
        id: 'exp-basic-scene-only',
        role: '实验组',
        name: '实验组二：仅场景增强',
        summary: '仅保留场景结构。',
        supportTags: ['模板', '工作流'],
        nodes: [
          node('基本信息获取', '用户问题', '故障与场景提取结果、知识库名、图谱检索方案素材', ['丢弃：图谱检索方案素材']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 章节模板文本', '预案正文', ['丢弃：图谱事实，仅保留场景结构'], '逐章并发')
        ]
      },
    ],
    inputs: ['雨后某220kV避雷器出现放电痕迹并伴随泄漏电流异常升高，请生成应急处置方案。', '电缆接头附近温度持续升高，并有焦糊味，后台出现绝缘告警，请生成处置方案。', '断路器保护发令后未动作，现场未见分闸，请生成包含检查确认和抢修措施的方案。'],
    expectedInput: '需要图谱事实补充故障原因、现象、措施、后果、风险和资源的问题。',
    expectedOutput: ['对照组应覆盖图谱事实。', '无图谱组和部分图谱组应暴露事实缺口。', '仅场景组用于观察缺少图谱事实时的泛化表达。'],
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
        summary: '无模板生成。',
        supportTags: ['图谱', '工作流'],
        nodes: [
          node('基本信息获取', '正式预案生成需求', '故障与场景提取结果、图谱检索方案素材、模板文本', ['丢弃：模板文本']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 图谱检索方案素材', '整篇预案正文', ['丢弃：章节模板文本'])
        ]
      },
      {
        id: 'exp-template-no-slice',
        role: '实验组',
        name: '实验组二：整模板单次生成',
        summary: '整模板单次生成。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '用户问题', '故障与场景提取结果、图谱检索方案素材、模板文本', ['保留：完整模板文本']),
          node('并行生成', '模板文本 + 图谱检索方案素材 + 故障与场景提取结果', '整篇预案正文', ['替换：章节模板 -> 完整模板'])
        ]
      },
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
          node('多故障基本信息获取', '多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果', ['保留：多个故障对象']),
          node('逐故障图谱检索', '设备表 + 故障列表', '逐故障图谱检索素材', ['逐故障并发查询图谱'], '逐故障并发'),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '用户问题 + 故障与场景提取结果 + 逐故障图谱检索素材 + 章节模板文本', '融合后的预案正文', ['保留：主次故障融合'], '逐章并发')
        ]
      },
      {
        id: 'exp-single-fault',
        role: '实验组',
        name: '实验组一：单故障普通链路',
        summary: '强制单故障。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '多故障用户问题', '单一故障场景、知识库名、图谱检索方案素材', ['丢弃：次生故障和伴随故障']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['变量固定：只保留主故障'], '逐章并发')
        ]
      },
      {
        id: 'exp-detect-no-per-fault-graph',
        role: '实验组',
        name: '实验组二：识别多故障但不逐项检索',
        summary: '不逐故障检索。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('多故障基本信息获取', '多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果', ['保留：故障列表']),
          node('基本信息获取', '主故障文本', '主故障图谱检索方案素材', ['替换：逐故障检索 -> 主故障检索']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障列表 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['丢弃：次生故障图谱素材'], '逐章并发')
        ]
      },
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
        summary: '移除场景约束。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '带约束用户问题', '故障与场景提取结果、图谱检索方案素材', ['丢弃：夜间/暴雨/保供/不停电约束']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['观察：与约束冲突的措施'], '逐章并发')
        ]
      },
      {
        id: 'exp-initial-constraint-only',
        role: '实验组',
        name: '实验组二：仅首轮注入约束',
        summary: '约束只进首轮。',
        supportTags: ['图谱', '模板', '工作流'],
        nodes: [
          node('基本信息获取', '带约束用户问题', '故障场景、约束信息、图谱检索方案素材', ['保留：约束信息']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障与场景提取结果 + 图谱检索方案素材 + 章节模板文本', '预案正文', ['丢弃：章节生成阶段约束信息'], '逐章并发')
        ]
      },
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

function ExperimentFlowDiagram({ planId, group }: { planId: string; group: ExperimentProcessGroup }) {
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
          const stepStatus = getExperimentStepStatus(experimentProgressByPlan[planId], group.id, index);
          return (
            <li className="experiment-plan-card__step-frame" key={`${flowNode.plugin}-${index}`}>
              <div className="experiment-plan-card__step-item">
                <div className="experiment-plan-card__step-header">
                  <Text strong>{index + 1}. {flowNode.plugin}</Text>
                  <Space size={6} wrap>
                    {flowNode.mode && flowNode.mode !== '主链路' ? <Tag color="gold">{flowNode.mode}</Tag> : null}
                    <Tag color={stepStatus === 'done' ? 'green' : stepStatus === 'failed' ? 'red' : stepStatus === 'running' ? 'blue' : 'default'}>
                      {experimentStepStatusText[stepStatus]}
                    </Tag>
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
                    {getRuntimeChanges(group, flowNode).length === 0 ? (
                      <Tag color="green">无变化</Tag>
                    ) : (
                      getRuntimeChanges(group, flowNode).map((variable) => (
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
              <div className="experiment-plan-card__top-row">
                <ExperimentSection title="实验目的">
                  <Paragraph className="experiment-plan-card__text">{plan.objective}</Paragraph>
                </ExperimentSection>
                <ExperimentSection title="实验输入与特征">
                  <Paragraph className="experiment-plan-card__text">{plan.expectedInput}</Paragraph>
                  <div className="experiment-plan-card__examples">
                    {plan.inputs.map((input) => (
                      <div className="experiment-plan-card__example" key={input}>{input}</div>
                    ))}
                  </div>
                </ExperimentSection>
              </div>
              <ExperimentSection title="实验过程" wide>
                <div className="experiment-plan-card__groups">
                  {plan.processGroups.map((group) => (
                    <div className={`experiment-plan-card__group is-${group.role === '对照组' ? 'control' : 'experiment'}`} key={group.id}>
                      <div className="experiment-plan-card__group-header">
                        <Tag color={group.role === '对照组' ? 'green' : 'blue'}>{splitGroupName(group).label}</Tag>
                        <Text strong>{splitGroupName(group).title}</Text>
                      </div>
                      <Paragraph className="experiment-plan-card__text">{group.summary}</Paragraph>
                      <ExperimentFlowDiagram planId={plan.id} group={group} />
                    </div>
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
