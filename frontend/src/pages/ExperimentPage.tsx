import { Button, Card, Popover, Segmented, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useEffect, useRef, useState } from 'react';
import { ALL_MULTI_FAULT_QUESTIONS, ALL_SINGLE_FAULT_QUESTIONS, EXPERIMENT_QUESTION_GROUPS } from '../data/presetQuestions';
import { ExperimentControlPanel, ExperimentEvaluationPanel, ExperimentFlowDiagram, ExperimentOutputPreview, ExperimentSection } from '../features/experiment/ExperimentPanels';
import { ExperimentQuestionPopover } from '../features/experiment/ExperimentQuestionPopover';
import { fetchExperimentPageSnapshot, fetchExperimentQuestionSuite, fetchExperimentRunDetail, fetchExperimentRuns, saveExperimentEvaluation, saveExperimentPageSnapshot, type ExperimentQuestionItem, type ExperimentQuestionSuite, type ExperimentRunSummary } from '../features/experiment/experimentApi';
import {
  defaultControlState,
  defaultEvaluationState,
  defaultOutputState,
  defaultStageState,
  type ExperimentCardView,
  type ExperimentControlStage,
  type ExperimentControlState,
  type ExperimentEvaluationScore,
  type ExperimentEvaluationState,
  type ExperimentEvaluationTask,
  type ExperimentFlowNode,
  type ExperimentOutputState,
  type ExperimentPageSnapshot,
  type ExperimentPlan,
  type ExperimentProcessGroup
} from '../features/experiment/experimentTypes';
import {
  addActiveGroup,
  buildExperimentPageSnapshot,
  eventQuestionItem,
  getMaxEvaluationConcurrency,
  getMaxExperimentConcurrency,
  getSuiteQuestionItems,
  isValidStructuredEvaluation,
  mergeRoundQuestionItem,
  parseEvaluationScore,
  pickRandomQuestionItems,
  questionItemLabel,
  removeActiveGroup,
  sanitizeControlStateMap,
  sanitizeEvaluationStateMap,
  splitGroupName
} from '../features/experiment/experimentUtils';
import { fetchTemplatePrompts } from '../features/quality/qualityApi';
import { loadPromptCache, savePromptCache } from '../features/quality/qualityStorage';

const { Paragraph, Text, Title } = Typography;

const BOUNDARY_QUESTION_SUITE_ID = 'boundary_input_boundary_v1';
const DISAMBIGUATION_QUESTION_SUITE_ID = 'disambiguation_device_subject_v1';
const GRAPH_TEMPLATE_QUESTION_SUITE_ID = 'graph_template_constraint_v1';
const MULTI_FAULT_QUESTION_SUITE_ID = 'multi_fault_chain_v1';

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
    title: '设备主体识别与消歧实验',
    tag: '消歧',
    objective: '验证当前工作流能从故障现象、位置参照、保护信号、相邻设备排除和伴随告警中识别真正故障主体。',
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
    inputs: ['断路器间隔附近保护通道退出，网管持续报R-LOS，开关位置和保护装置本体均正常，请判断故障主体并生成处置方案。', '备自投未启动，后台显示母线电压消失，但现场母线仍带电且负荷正常，请判断故障主体并生成现场方案。', '站内光缆经过断路器间隔，断路器运行正常但保护通道退出，网管报R-LOS，请判断故障主体并生成处置方案。'],
    expectedInput: '包含干扰设备、位置修饰词或现象链，但只有一个真实故障主体的问题。',
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
    questionSuiteId: GRAPH_TEMPLATE_QUESTION_SUITE_ID,
    inputs: ['雨后某220kV避雷器出现放电痕迹并伴随泄漏电流异常升高，请生成应急处置方案。', '断路器保护发令后未动作，现场未见分闸，请生成包含检查确认和抢修措施的方案。', '某电缆接头击穿起火，请生成包含响应终止和恢复验证的完整预案。'],
    expectedInput: '同时依赖图谱事实补充和模板章节约束的正式预案生成问题。',
    expectedOutput: ['对照组应兼顾事实覆盖和章节结构。', '移除图谱组用于观察原因、措施、风险和资源缺口。', '移除模板组用于观察章节缺失、重复和串章。'],
    metrics: ['事实覆盖度', '措施覆盖度', '章节完整率', '章节边界稳定性']
  },
  {
    id: 'multiFault',
    title: '多故障链式实验',
    tag: '链式',
    objective: '验证多故障模式能识别同一设备内链式或并发故障，并将逐故障图谱检索结果融合进统一处置方案。',
    processGroups: [
      {
        ...completeWorkflowGroup,
        nodes: [
          node('多故障基本信息获取', '单设备多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果', ['保留：同设备多个故障节点']),
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
          node('基本信息获取', '单设备多故障用户问题', '单一故障场景、知识库名、图谱检索方案素材', ['仅单故障']),
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
          node('多故障基本信息获取', '单设备多故障用户问题', '用户问题、设备表、故障列表、主故障、故障与场景提取结果'),
          node('主故障图谱检索', '设备表 + 主故障', '主故障图谱检索方案素材', ['仅主故障图谱']),
          node('模板切片', '当前模板配置', '章节列表、章节模板文本', ['无上游变量：读取 llmkg_templates 当前模板']),
          node('并行生成', '故障列表 + 主故障图谱检索方案素材 + 章节模板文本', '预案正文', ['无次生图谱'])
        ]
      },
    ],
    questionSuiteId: MULTI_FAULT_QUESTION_SUITE_ID,
    inputs: ['某110kV断路器保护发令后拒分，机构箱无动作声，储能电机反复启动且控制回路接地告警，请生成完整预案。', '某电缆中间接头局放升高后温度快速上升，护层接地电流异常并出现焦糊味，请生成应急方案。', '某主变轻瓦斯动作后油位下降，油色谱异常且冷却器不能自动投入，请生成处置方案。'],
    expectedInput: '同一设备中出现多个故障点、多个异常或先后诱发关系的问题。',
    expectedOutput: ['输出应识别同一设备内多个故障。', '输出应区分主故障、伴随故障和受影响功能。', '实验组用于观察同设备次生故障遗漏和逐故障素材缺失。'],
    metrics: ['故障拆解率', '主次识别正确率', '逐故障图谱覆盖率', '融合处置完整度']
  }
];

async function runEvaluationRequest(
  prompt: string,
  content: string,
  context: { question: string; questionGroup?: string; groupLabel: string; groupTitle: string; round: number },
  onUpdate?: (patch: Partial<Pick<ExperimentEvaluationScore, 'comment' | 'score'>>) => void
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
      structured: false,
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
  let reasoningText = '';

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
    if (eventName === 'quality_reasoning_chunk') {
      reasoningText += String(data?.chunk || '');
      return;
    }
    if (eventName === 'quality_done') {
      applyOutput(String(data?.output_text || outputText));
      reasoningText = String(data?.reasoning_text || reasoningText);
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

  return {
    score: parseEvaluationScore(outputText),
    comment: outputText || '评估完成，但未返回说明。',
    reasoningText
  };
}

async function runStructuredEvaluationRequest(
  context: { question: string; questionGroup?: string; groupLabel: string; groupTitle: string },
  outputText: string,
  reasoningText: string
) {
  const experimentGroup = `${context.groupLabel} ${context.groupTitle}`.trim();
  let lastError = '';
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    const response = await fetch('/api/quality/structured', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        outputText,
        reasoningText,
        structuredContext: {
          question: context.question,
          questionGroup: context.questionGroup || '',
          experimentGroup
        }
      })
    });
    const text = await response.text();
    let data: any = {};
    if (text.trim()) {
      try {
        data = JSON.parse(text);
      } catch {
        lastError = `结构化评估响应不是有效 JSON：${text.slice(0, 160)}`;
        continue;
      }
    }
    if (!response.ok) {
      lastError = data?.message || `结构化评估请求失败：${response.status}`;
      continue;
    }
    const structuredEvaluation = data?.structured_evaluation && typeof data.structured_evaluation === 'object'
      ? data.structured_evaluation as Record<string, any>
      : undefined;
    if (isValidStructuredEvaluation(structuredEvaluation, `${outputText}\n${reasoningText}`)) {
      return structuredEvaluation;
    }
    lastError = '结构化评估结果无效，已单独重跑仍未得到有效 JSON';
  }
  throw new Error(lastError || '结构化评估失败');
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
  const [evaluationCompactModeMap, setEvaluationCompactModeMap] = useState<Record<string, boolean>>({});
  const databaseQuestionCount = Object.values(questionSuiteMap).reduce((total, suite) => total + suite.questionCount, 0) || experimentQuestionCount;
  const controlTimerMap = useRef<Record<string, number>>({});
  const snapshotReadyRef = useRef(false);
  const snapshotSaveTimerRef = useRef<number | undefined>(undefined);

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

  useEffect(() => {
    let cancelled = false;
    fetchExperimentPageSnapshot()
      .then((snapshot) => {
        if (cancelled || !snapshot || typeof snapshot !== 'object') return;
        const pageSnapshot = snapshot as ExperimentPageSnapshot;
        setCardViewMap(pageSnapshot.cardViewMap || {});
        setControlStateMap(sanitizeControlStateMap(pageSnapshot.controlStateMap || {}));
        setOutputStateMap(pageSnapshot.outputStateMap || {});
        setEvaluationStateMap(sanitizeEvaluationStateMap(pageSnapshot.evaluationStateMap || {}));
        setSampledQuestionMap(pageSnapshot.sampledQuestionMap || {});
        setSelectedRunIdMap(pageSnapshot.selectedRunIdMap || {});
        setEvaluationCompactModeMap(pageSnapshot.evaluationCompactModeMap || {});
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) snapshotReadyRef.current = true;
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!snapshotReadyRef.current) return;
    if (snapshotSaveTimerRef.current) window.clearTimeout(snapshotSaveTimerRef.current);
    snapshotSaveTimerRef.current = window.setTimeout(() => {
      const snapshot = buildExperimentPageSnapshot({
        cardViewMap,
        controlStateMap,
        outputStateMap,
        evaluationStateMap,
        sampledQuestionMap,
        selectedRunIdMap,
        evaluationCompactModeMap
      });
      void saveExperimentPageSnapshot(snapshot).catch(() => {});
    }, 800);
  }, [cardViewMap, controlStateMap, outputStateMap, evaluationStateMap, sampledQuestionMap, selectedRunIdMap, evaluationCompactModeMap]);

  useEffect(() => () => {
    Object.values(controlTimerMap.current).forEach((timerId) => window.clearInterval(timerId));
    if (snapshotSaveTimerRef.current) window.clearTimeout(snapshotSaveTimerRef.current);
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
            setSampledQuestionMap((prev) => prev[plan.id]?.length ? prev : ({
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

    const patchSavedScore = (task: ExperimentEvaluationTask, patch: Partial<ExperimentEvaluationScore>) => {
      const roundKey = String(task.round);
      const current = savedScores[roundKey]?.[task.group.id];
      if (!current) return;
      savedScores = {
        ...savedScores,
        [roundKey]: {
          ...(savedScores[roundKey] || {}),
          [task.group.id]: { ...current, ...patch }
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
        const evaluationContext = {
          question: task.output.question || outputState.roundQuestions[String(task.round)] || '',
          questionGroup: questionItemLabel(task.output.questionItem || outputState.roundQuestionItems?.[String(task.round)]),
          groupLabel: groupTitle.label,
          groupTitle: groupTitle.title,
          round: task.round
        };
        const result = await runEvaluationRequest(planEvaluationPrompt, task.output.outputText, evaluationContext, (patch) => {
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
          comment: result.comment
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
        void runStructuredEvaluationRequest(evaluationContext, result.comment, result.reasoningText)
          .then((structuredEvaluation) => {
            const structuredScore = Number(structuredEvaluation?.score);
            const structuredPatch: Partial<ExperimentEvaluationScore> = {
              structuredEvaluation,
              structuredError: undefined,
              score: Number.isFinite(structuredScore) ? Math.max(0, Math.min(10, structuredScore)) : result.score
            };
            patchSavedScore(task, structuredPatch);
            updateEvaluationState(planId, (current) => ({
              ...current,
              scores: {
                ...current.scores,
                [String(task.round)]: {
                  ...(current.scores[String(task.round)] || {}),
                  [task.group.id]: {
                    ...(current.scores[String(task.round)]?.[task.group.id] || doneScore),
                    ...structuredPatch,
                    status: 'done'
                  }
                }
              }
            }));
            const progress = Math.round((completed / tasks.length) * 100);
            persistEvaluation(completed >= tasks.length ? 'done' : 'running', progress);
          })
          .catch((error) => {
            const structuredPatch: Partial<ExperimentEvaluationScore> = {
              structuredError: error instanceof Error ? error.message : '结构化评估失败'
            };
            patchSavedScore(task, structuredPatch);
            updateEvaluationState(planId, (current) => ({
              ...current,
              scores: {
                ...current.scores,
                [String(task.round)]: {
                  ...(current.scores[String(task.round)] || {}),
                  [task.group.id]: {
                    ...(current.scores[String(task.round)]?.[task.group.id] || doneScore),
                    ...structuredPatch,
                    status: 'done'
                  }
                }
              }
            }));
            const progress = Math.round((completed / tasks.length) * 100);
            persistEvaluation(completed >= tasks.length ? 'done' : 'running', progress);
          });
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
          </Space>
          <Button type="primary" icon={<PlayCircleOutlined />} disabled>
            批量运行实验
          </Button>
        </div>
        <div className="experiment-hero-card__overview">
          <Paragraph className="experiment-hero-card__desc">
            基于现有示例题集和已接入插件，后续可在这里批量运行消融实验、压力测试和效率测试，集中展示当前工作流在边界拦截、主体消歧、图谱增强、模板结构和多故障处理上的优势。
          </Paragraph>
          <Space wrap className="experiment-hero-card__stats">
            <Tag color="blue">单故障题 {ALL_SINGLE_FAULT_QUESTIONS.length} 条</Tag>
            <Tag color="red">多故障题 {ALL_MULTI_FAULT_QUESTIONS.length} 条</Tag>
            <Tag color="geekblue">数据库实验题 {databaseQuestionCount} 条</Tag>
            <Tag color="green">复用现有 FastGPT 插件</Tag>
          </Space>
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
                evaluationState={evaluationStateMap[plan.id] || defaultEvaluationState}
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
                    outputState={outputStateMap[plan.id] || defaultOutputState}
                    evaluationState={evaluationStateMap[plan.id] || defaultEvaluationState}
                    runs={runRecordMap[plan.id] || []}
                    selectedRunId={selectedRunIdMap[plan.id]}
                    evaluationRunning={getControlState(plan.id).evaluation.status === 'running'}
                    evaluationConcurrency={getControlState(plan.id).evaluationConcurrency}
                    compactMode={Boolean(evaluationCompactModeMap[plan.id])}
                    onUpdateEvaluationConcurrency={(value) => updateControlConfig(plan.id, { evaluationConcurrency: value })}
                    onSelectRun={(runId) => setSelectedRunIdMap((prev) => ({ ...prev, [plan.id]: runId }))}
                    onLoadRun={() => void loadExperimentRun(plan)}
                    onRefreshRuns={() => void refreshExperimentRuns(plan.id)}
                    onRunEvaluation={() => void runControlStage(plan, 'evaluation')}
                    onToggleCompactMode={(value) => setEvaluationCompactModeMap((prev) => ({ ...prev, [plan.id]: value }))}
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
