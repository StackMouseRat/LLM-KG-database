import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Button, Card, Checkbox, Collapse, Input, Layout, message, Space, Switch, Tag, Typography } from 'antd';
import { CopyOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { PipelineCaseSearchCard, PipelineChapter, PipelineRunResponse, PipelineStage } from './types/plan';
import { RichTextRenderer } from './components/RichTextRenderer';
import { LoginPage } from './pages/LoginPage';
import { fetchCurrentUser, login, logout } from './services/authApi';
import { runPipelineStream } from './services/planApi';
import { downloadText } from './utils/download';

const { Header, Content } = Layout;
const { TextArea } = Input;
const PLAN_SNAPSHOT_KEY = 'llmkg_saved_plan_snapshot_v1';
const MODE_TAGS_VISIBLE_KEY = 'llmkg_mode_tags_visible_v1';
const COMPACT_LAYOUT_KEY = 'llmkg_compact_layout_v1';
const DARK_MODE_KEY = 'llmkg_dark_mode_v1';

type RouteKey = 'plan' | 'trace' | 'quality' | 'template';
type AppRoute = RouteKey | 'login';
type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated';
type UserGroup = 'admin' | 'user';

const TraceGraphPage = lazy(() => import('./pages/TraceGraphPage').then((module) => ({ default: module.TraceGraphPage })));
const QualityReviewPage = lazy(() =>
  import('./pages/QualityReviewPage').then((module) => ({ default: module.QualityReviewPage }))
);
const TemplateViewPage = lazy(() =>
  import('./pages/TemplateViewPage').then((module) => ({ default: module.TemplateViewPage }))
);

const routeItems: Array<{ key: RouteKey; label: string; path: string }> = [
  { key: 'plan', label: '预案生成', path: '/plan' },
  { key: 'trace', label: '图谱溯源', path: '/trace' },
  { key: 'quality', label: '格式优化与质量评估', path: '/quality' },
  { key: 'template', label: '模板查看', path: '/template' }
];

const PRESET_QUESTIONS: Record<string, string[]> = {
  高压断路器: [
    '雷雨后某 110kV 变电站线路断路器拒合，后台报机构异常，夜间值班，无法立即停电大修，请生成一份现场应急处置方案。',
    '某 35kV 断路器液压机构渗油，当前仍带负荷运行，需要先控风险再安排检修，请生成一份双阶段处置方案。',
    '断路器触头发热并伴随异味，运行人员已发现异常但尚未跳闸，请生成一份简短的先期处置和恢复运行方案。'
  ],
  变压器: [
    '暴雨后主变轻瓦斯频繁报警，油位异常，夜间值班且不能长时间停电，请生成一份双阶段处置方案。',
    '某 220kV 主变套管接点持续过热，现场测温升高，要求生成一份先期控制与后续检修结合的应急方案。',
    '夏季高负荷下主变油温过高，冷却器运行异常，无法立即更换设备，请生成一份简短应急预案。'
  ],
  电力电缆: [
    '暴雨导致电缆沟进水，开关柜出现绝缘告警，夜间值班，无法立即更换设备，需要一份简短的双阶段处置方案。',
    '某配电电缆中间接头疑似受潮放电，现场有烧焦气味，请生成一份现场隔离、故障确认和抢修恢复方案。',
    '电力电缆绝缘劣化与击穿故障导致线路停运，请生成一份包含故障定位、开挖抢修和恢复验证的应急方案。'
  ],
  互感器: [
    '某 110kV 电压互感器接线盒渗油，现场暂无明显发热，请生成一份应急处置与后续检修方案。',
    '220kV 电流互感器末屏接地异常并伴随放电痕迹，请生成一份风险控制优先的处置预案。',
    '35kV 母线 TV 高压熔断器熔断后电压异常，要求生成一份现场核查和恢复运行方案。'
  ],
  光缆: [
    '传输机房出现 2M 业务中断，怀疑光缆接续异常，请生成一份夜间现场排查和恢复方案。',
    '某段光缆疑似被外力损伤导致业务中断，要求生成一份快速定位和抢修恢复方案。',
    '雨后光缆接头盒附近出现异常告警，怀疑受潮，请生成一份现场检查与应急处置方案。'
  ],
  环网柜: [
    '户外环网柜内部疑似受潮，开闭器动作异常，请生成一份现场隔离与抢修恢复方案。',
    '环网柜防凝露设计不良导致柜内绝缘风险升高，请生成一份临时控制和后续整改方案。',
    '某环网柜自动化信号异常并影响运行监视，请生成一份简短应急处置预案。'
  ],
  避雷器: [
    '雷雨天气后避雷器疑似阀片击穿，线路出现接地异常，请生成一份现场应急处置方案。',
    '某配电线路避雷器表面存在放电痕迹并伴随污闪风险，请生成一份隔离与巡检加强方案。',
    '降雪后避雷器高压端疑似沿面侧闪，要求生成一份风险控制和恢复运行方案。'
  ],
  杆塔: [
    '持续暴雨后杆塔基础冲刷严重并出现倾斜迹象，请生成一份现场隔离、风险研判和抢修方案。',
    '大风天气后发现输电杆塔构件松动，线路暂未跳闸，请生成一份先期处置和后续加固方案。',
    '某塔位附近山体滑坡，杆塔受力异常，要求生成一份夜间应急处置方案。'
  ],
  输电线路: [
    '雷击导致输电线路跳闸并重合不成功，请生成一份故障巡视、研判和恢复运行方案。',
    '导线覆冰严重，存在舞动和断线风险，请生成一份防风险和应急处置方案。',
    '外力施工导致输电线路异常停运，要求生成一份现场控制与抢修恢复方案。'
  ]
};

const MULTI_FAULT_PRESET_QUESTIONS: Record<string, string[]> = {
  高压断路器: [
    '某110kV断路器同时出现控制回路短路故障和合分闸控制回路故障，请生成一份现场应急处置方案。',
    '某变电站断路器同时出现辅助开关及转换接点异常故障、合分闸线圈故障和拒动故障，请生成一份故障处置与恢复方案。',
    '某高压断路器同时出现导电回路直阻超标故障、触头及导电连接异常故障和绝缘不良故障，请生成一份应急预案。'
  ],
  变压器: [
    '某主变同时出现轻瓦斯报警和油温过高异常，请生成一份先期控制与后续检修方案。',
    '某220kV主变同时出现套管接头过热、冷却器运行异常和油位异常，请生成一份应急处置方案。',
    '某变压器同时出现有载调压异常和渗油缺陷，请生成一份双阶段处置方案。'
  ],
  电力电缆: [
    '某配电电缆同时出现中间接头受潮放电和终端头发热异常，请生成一份现场隔离与抢修方案。',
    '某电力电缆同时出现绝缘劣化、局部放电和中间接头异味，请生成一份故障确认与恢复方案。',
    '暴雨后某电缆线路同时出现电缆沟进水和接头击穿故障，请生成一份应急处置预案。'
  ],
  互感器: [
    '某电流互感器同时出现渗油和末屏接地异常，请生成一份应急处置方案。',
    '某电压互感器同时出现高压熔断器熔断和异常放电痕迹，请生成一份现场处置方案。',
    '某互感器同时出现发热和绝缘异常告警，请生成一份风险控制与恢复方案。'
  ],
  光缆: [
    '某段光缆同时出现业务中断和接头盒受潮告警，请生成一份排查恢复方案。',
    '某光缆同时出现外力损伤和接续点衰耗异常，请生成一份应急抢修方案。',
    '雨后某通信光缆同时出现链路中断与机房告警异常，请生成一份现场处置方案。'
  ],
  环网柜: [
    '某环网柜同时出现柜内受潮和开闭器动作异常，请生成一份应急处置方案。',
    '某环网柜同时出现绝缘告警、凝露异常和遥信异常，请生成一份现场处置方案。',
    '某户外环网柜同时出现自动化信号异常和局部放电风险，请生成一份双阶段方案。'
  ],
  避雷器: [
    '雷雨后某避雷器同时出现阀片击穿故障和沿面闪络故障，请生成一份应急处置方案。',
    '某线路避雷器同时出现侧闪痕迹和未有效动作故障，请生成一份排查与恢复方案。',
    '某配电避雷器同时出现脱落接地故障和表面放电异常，请生成一份现场处置方案。'
  ],
  杆塔: [
    '持续暴雨后某杆塔同时出现基础冲刷和构件松动故障，请生成一份应急处置方案。',
    '某输电杆塔同时出现倾斜迹象、拉线异常和基础开裂，请生成一份抢险方案。',
    '大风天气后某杆塔同时出现塔材变形和螺栓松动，请生成一份现场处置预案。'
  ],
  输电线路: [
    '某输电线路同时出现雷击跳闸和导线覆冰异常，请生成一份应急处置方案。',
    '某线路同时出现外力破坏和接地故障，请生成一份现场控制与抢修方案。',
    '某输电线路同时出现舞动风险、绝缘子闪络和局部放电迹象，请生成一份处置方案。'
  ]
};

const ALL_PRESET_QUESTIONS = Object.values(PRESET_QUESTIONS).flat();
const ALL_MULTI_FAULT_PRESET_QUESTIONS = Object.values(MULTI_FAULT_PRESET_QUESTIONS).flat();

const stageText: Record<PipelineStage, string> = {
  idle: '等待输入',
  basic_info: '正在获取基本信息',
  template_split: '正在切分模板',
  parallel_generating: '正在并行生成章节',
  case_search: '正在检索案例',
  done: '生成完成',
  error: '生成失败'
};

const chapterStatusText: Record<'pending' | 'running' | 'done' | 'error', string> = {
  pending: '等待中',
  running: '生成中',
  done: '已完成',
  error: '失败'
};

function renderInlineText(text: string, showModeTags: boolean): ReactNode[] {
  const parts = text.split(/(\[KG\]|\[GEN\]|\[FIX\]|\*\*[^*]+\*\*)/g);
  return parts
    .filter((part) => part !== '')
    .map((part, index) => {
      if (part === '[KG]') {
        if (!showModeTags) return null;
        return (
          <Tag color="blue" key={index}>
            KG
          </Tag>
        );
      }
      if (part === '[GEN]') {
        if (!showModeTags) return null;
        return (
          <Tag color="orange" key={index}>
            GEN
          </Tag>
        );
      }
      if (part === '[FIX]') {
        if (!showModeTags) return null;
        return (
          <Tag color="green" key={index}>
            FIX
          </Tag>
        );
      }
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return <span key={index}>{part}</span>;
    });
}

function renderMarkedText(text: string, options?: { normalize?: boolean; stripMeta?: boolean; showModeTags?: boolean }) {
  const rawText = options?.normalize === false ? String(text || '') : normalizeRenderedOutput(text);
  const lineSplitText = splitTagLeadingParagraphs(rawText);
  const normalizedText = options?.stripMeta === false ? lineSplitText : cleanupInlineMetaLines(lineSplitText);
  const showModeTags = options?.showModeTags ?? true;
  return (
    <div className="rendered-rich-text">
      {normalizedText.split('\n').map((line, index) => {
        const trimmed = line.trim();

        if (!trimmed) {
          return <div className="render-blank" key={index} />;
        }

        if (trimmed.startsWith('#### ')) {
          return (
            <div className="render-h4" key={index}>
              {renderInlineText(trimmed.slice(5), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('### ')) {
          return (
            <div className="render-h3" key={index}>
              {renderInlineText(trimmed.slice(4), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('## ')) {
          return (
            <div className="render-h2" key={index}>
              {renderInlineText(trimmed.slice(3), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('# ')) {
          return (
            <div className="render-h1" key={index}>
              {renderInlineText(trimmed.slice(2), showModeTags)}
            </div>
          );
        }

        return (
          <div className="render-line" key={index}>
            {renderInlineText(line, showModeTags)}
          </div>
        );
      })}
    </div>
  );
}

function normalizeRenderedOutput(text: string) {
  const raw = String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/([^\n])(\[(?:KG|GEN|FIX)\])/g, '$1\n$2')
    .replace(/([^\n])(#{1,4}\s+)/g, '$1\n$2')
    .replace(/([^\n])(第[一二三四五六七八九十0-9]+章)/g, '$1\n$2')
    .replace(/([^\n])(案例[一二三四五六七八九十百千0-9]+[：:\s])/g, '$1\n$2')
    .replace(/([^\n])(---+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\s+)/g, '$1\n$2')
    .replace(/([^\n])(内容来源：|图谱字段：|预定义文本：|生成要求：)/g, '$1\n$2');
  const headingPattern = /(^|\n)(#{1,4}\s+[^\n]+|第[一二三四五六七八九十0-9]+章[^\n]*)/m;
  const match = raw.match(headingPattern);

  if (!match || typeof match.index !== 'number') {
    return promoteStructuredHeadings(raw);
  }

  const startIndex = match[1] ? match.index + match[1].length : match.index;
  return promoteStructuredHeadings(raw.slice(startIndex).trimStart());
}

function splitTagLeadingParagraphs(text: string) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\s*(\[(?:KG|GEN|FIX)\])\s*/g, '\n$1 ')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

function cleanupInlineMetaLines(text: string) {
  const patterns = ['内容来源：', '图谱字段：', '预定义文本：', '生成要求：'];
  return text
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) return true;
      if (/^!\[.*\]\(.*\)$/.test(trimmed)) return false;
      if (/^\[图像内容省略\]$/.test(trimmed)) return false;
      return !patterns.some((marker) => trimmed.includes(marker));
    })
    .join('\n');
}

function promoteStructuredHeadings(text: string) {
  const lines = text.split('\n');
  const normalized: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    let line = lines[i].trim();

    if (!line) {
      normalized.push('');
      continue;
    }

    if (/^#{1,6}$/.test(line)) {
      continue;
    }

    if (/^GEN/.test(line)) {
      line = line.replace(/^GEN/, '').trim();
    } else if (/^KG/.test(line)) {
      line = line.replace(/^KG/, '').trim();
    } else if (/^FIX/.test(line)) {
      line = line.replace(/^FIX/, '').trim();
    }

    if (!line) {
      continue;
    }

    if (/^第[一二三四五六七八九十百千0-9]+章\s+.+$/.test(line)) {
      normalized.push(`# ${line}`);
      continue;
    }

    if (/^案例[一二三四五六七八九十百千0-9]+[：:\s].+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^---+$/.test(line)) {
      normalized.push('');
      continue;
    }

    normalized.push(line);
  }

  return normalized.join('\n');
}

function parseFaultScene(text: string) {
  try {
    return JSON.parse(text || '{}') as Record<string, unknown>;
  } catch {
    return {};
  }
}

function routeFromPath(pathname: string): AppRoute {
  if (pathname === '/login') return 'login';
  if (pathname === '/trace') return 'trace';
  if (pathname === '/quality') return 'quality';
  if (pathname === '/template') return 'template';
  return 'plan';
}

function loadSavedSnapshot(): { question: string; pipeline: PipelineRunResponse } | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PLAN_SNAPSHOT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.question !== 'string') return null;
    if (!parsed.pipeline || typeof parsed.pipeline !== 'object') return null;
    return {
      question: parsed.question,
      pipeline: parsed.pipeline as PipelineRunResponse
    };
  } catch {
    return null;
  }
}

function loadModeTagsVisible() {
  if (typeof window === 'undefined') return true;
  const raw = window.localStorage.getItem(MODE_TAGS_VISIBLE_KEY);
  if (raw == null) return true;
  return raw !== '0';
}

function loadCompactLayout() {
  if (typeof window === 'undefined') return false;
  const raw = window.localStorage.getItem(COMPACT_LAYOUT_KEY);
  if (raw == null) return false;
  return raw === '1';
}

function loadDarkMode() {
  if (typeof window === 'undefined') return false;
  const raw = window.localStorage.getItem(DARK_MODE_KEY);
  if (raw == null) return false;
  return raw === '1';
}

function saveSnapshot(question: string, pipeline: PipelineRunResponse) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(
    PLAN_SNAPSHOT_KEY,
    JSON.stringify({
      question,
      pipeline
    })
  );
}

function pickRandomPresetQuestion(enableMultiFault = false) {
  const pool = enableMultiFault ? ALL_MULTI_FAULT_PRESET_QUESTIONS : ALL_PRESET_QUESTIONS;
  if (!pool.length) {
    return '';
  }
  const index = Math.floor(Math.random() * pool.length);
  return pool[index];
}

export default function App() {
  const savedSnapshot = loadSavedSnapshot();
  const [route, setRoute] = useState<AppRoute>(() =>
    typeof window === 'undefined' ? 'login' : routeFromPath(window.location.pathname)
  );
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking');
  const [currentUsername, setCurrentUsername] = useState('');
  const [currentUserGroup, setCurrentUserGroup] = useState<UserGroup>('user');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginErrorMessage, setLoginErrorMessage] = useState('');
  const [showModeTags, setShowModeTags] = useState(loadModeTagsVisible);
  const [showCompactLayout, setShowCompactLayout] = useState(loadCompactLayout);
  const [darkMode, setDarkMode] = useState(loadDarkMode);
  const [question, setQuestion] = useState(savedSnapshot?.question || pickRandomPresetQuestion());
  const [pipeline, setPipeline] = useState<PipelineRunResponse | null>(savedSnapshot?.pipeline || null);
  const [stage, setStage] = useState<PipelineStage>(savedSnapshot?.pipeline ? 'done' : 'idle');
  const [nodeStageLabel, setNodeStageLabel] = useState(savedSnapshot?.pipeline ? '已恢复上次生成结果' : '等待输入');
  const [loading, setLoading] = useState(false);
  const [enableCaseSearch, setEnableCaseSearch] = useState(false);
  const [enableMultiFaultSearch, setEnableMultiFaultSearch] = useState(false);
  const [savedFlag, setSavedFlag] = useState(Boolean(savedSnapshot?.pipeline));

  const chapters = pipeline?.chapters ?? [];
  const mergedOutput = useMemo(
    () => chapters.map((item) => `# ${item.chapterNo} ${item.title}\n\n${item.outputText}`).join('\n\n'),
    [chapters]
  );

  const summaryTags = useMemo(() => {
    if (!pipeline) return [];
    const parsed = parseFaultScene(pipeline.basicInfo.faultScene);
    const faultNodes = parsed['故障二级节点'];
    const faultTags = Array.isArray(faultNodes)
      ? faultNodes.map((item) => String(item)).filter(Boolean)
      : faultNodes
        ? [String(faultNodes)]
        : [];
    return [
      ...faultTags,
      parsed['故障对象'] ? String(parsed['故障对象']) : '',
      pipeline.templateSplit.templateName,
      `${pipeline.templateSplit.chapterCount}章`
    ].filter(Boolean) as string[];
  }, [pipeline]);
  const caseCards = useMemo(() => pipeline?.caseSearch?.cards || [], [pipeline?.caseSearch?.cards]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname));
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(MODE_TAGS_VISIBLE_KEY, showModeTags ? '1' : '0');
  }, [showModeTags]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(COMPACT_LAYOUT_KEY, showCompactLayout ? '1' : '0');
  }, [showCompactLayout]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(DARK_MODE_KEY, darkMode ? '1' : '0');
    document.body.classList.toggle('theme-dark', darkMode);
  }, [darkMode]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncAuth = async () => {
      try {
        const session = await fetchCurrentUser();
        if (session?.username) {
          setCurrentUsername(session.username);
          setCurrentUserGroup(session.group);
          setAuthStatus('authenticated');
        } else {
          setCurrentUsername('');
          setCurrentUserGroup('user');
          setAuthStatus('unauthenticated');
        }
      } catch (error) {
        setCurrentUsername('');
        setCurrentUserGroup('user');
        setAuthStatus('unauthenticated');
        message.error(error instanceof Error ? error.message : '登录状态校验失败');
      }
    };

    void syncAuth();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || authStatus === 'checking') return;

    if (authStatus === 'unauthenticated') {
      if (window.location.pathname !== '/login') {
        window.history.replaceState(null, '', '/login');
      }
      setRoute('login');
      return;
    }

    if (window.location.pathname === '/' || window.location.pathname === '/login') {
      window.history.replaceState(null, '', '/plan');
      setRoute('plan');
      return;
    }

    setRoute(routeFromPath(window.location.pathname));
  }, [authStatus]);

  const navigateRoute = (nextRoute: RouteKey) => {
    if (authStatus !== 'authenticated') return;
    const target = routeItems.find((item) => item.key === nextRoute);
    if (!target || typeof window === 'undefined') return;
    if (window.location.pathname !== target.path) {
      window.history.pushState(null, '', target.path);
    }
    setRoute(nextRoute);
  };

  const handleLogin = async (username: string, password: string) => {
    if (!username || !password) {
      setLoginErrorMessage('请输入用户名和密码');
      message.warning('请输入用户名和密码');
      return;
    }

    setLoginLoading(true);
    setLoginErrorMessage('');
    try {
      const session = await login(username, password);
      setCurrentUsername(session.username);
      setCurrentUserGroup(session.group);
      setAuthStatus('authenticated');
      if (typeof window !== 'undefined') {
        window.history.replaceState(null, '', '/plan');
      }
      setRoute('plan');
      message.success('登录成功');
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : '登录失败';
      setLoginErrorMessage(nextMessage);
      message.error(nextMessage);
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登出失败');
    } finally {
      setCurrentUsername('');
      setCurrentUserGroup('user');
      setAuthStatus('unauthenticated');
      if (typeof window !== 'undefined') {
        window.history.replaceState(null, '', '/login');
      }
      setRoute('login');
    }
  };

  const handleGenerate = async () => {
    if (!question.trim()) {
      message.warning('请先输入故障场景描述');
      return;
    }

    setLoading(true);
    setPipeline({
      question,
      basicInfo: {
        userQuestion: question,
        faultScene: '',
        graphMaterial: ''
      },
      templateSplit: {
        templateId: '',
        templateName: '',
        currentVersion: '',
        chapterCount: 0
      },
      chapters: []
    });
    setStage('basic_info');
    setNodeStageLabel('正在获取基本信息');

    try {
      await runPipelineStream(
        { question, enableCaseSearch, enableMultiFaultSearch },
        {
          onStage: (nextStage) => {
            if (nextStage === 'basic_info') {
              setStage('basic_info');
              setNodeStageLabel('正在获取基本信息');
            }
            if (nextStage === 'template_split') {
              setStage('template_split');
              setNodeStageLabel('正在切分模板');
            }
            if (nextStage === 'parallel_generating') {
              setStage('parallel_generating');
              setNodeStageLabel('正在并行生成章节');
            }
            if (nextStage === 'case_search') {
              setNodeStageLabel('正在并行生成章节并检索案例');
            }
          },
          onTemplateSplit: (payload) => {
            setPipeline((prev) => ({
              question: prev?.question || question,
              basicInfo: prev?.basicInfo || {
                userQuestion: question,
                faultScene: '',
                graphMaterial: ''
              },
              templateSplit: payload?.templateSplit || {
                templateId: '',
                templateName: '',
                currentVersion: '',
                chapterCount: 0
              },
              chapters: (payload?.chapters || []).map((chapter: any) => ({
                chapterNo: String(chapter.chapterNo || ''),
                title: String(chapter.title || ''),
                sectionCount: Number(chapter.sectionCount || 0),
                templateText: String(chapter.templateText || ''),
                outputText: '',
                status: 'pending'
              })),
              caseSearch:
                prev?.caseSearch ||
                (enableCaseSearch
                  ? {
                      enabled: true,
                      status: 'idle'
                    }
                  : undefined)
            }));
          },
          onChapterStarted: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? { ...chapter, status: 'running' }
                    : chapter
                )
              };
            });
          },
          onChapterDone: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? {
                        ...chapter,
                        outputText: String(payload?.outputText || ''),
                        elapsedSec: typeof payload?.elapsedSec === 'number' ? payload.elapsedSec : undefined,
                        status: payload?.status === 'error' ? 'error' : 'done'
                      }
                    : chapter
                )
              };
            });
          },
          onChapterChunk: (payload) => {
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                chapters: prev.chapters.map((chapter) =>
                  chapter.chapterNo === String(payload?.chapterNo || '')
                    ? {
                        ...chapter,
                        outputText: `${chapter.outputText || ''}${String(payload?.chunk || '')}`,
                        status: 'running'
                      }
                    : chapter
                )
              };
            });
          },
          onCaseSearchStarted: (payload) => {
            setNodeStageLabel('正在并行生成章节并检索案例');
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: 'running',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: '',
                  cards: prev.caseSearch?.cards || []
                }
              };
            });
          },
          onCaseSearchDone: (payload) => {
            setStage('done');
            setNodeStageLabel('生成完成');
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: 'done',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: payload?.output_text ? String(payload.output_text) : '',
                  cards: Array.isArray(payload?.cards) ? payload.cards : []
                }
              };
            });
          },
          onCaseSearchError: (payload) => {
            if (payload?.status === 'skipped') {
              setStage('done');
              setNodeStageLabel('生成完成');
            } else {
              setStage('error');
              setNodeStageLabel('案例检索失败');
            }
            setPipeline((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                caseSearch: {
                  enabled: true,
                  status: payload?.status === 'skipped' ? 'skipped' : 'error',
                  kbName: payload?.kb_name ? String(payload.kb_name) : undefined,
                  datasetId: payload?.dataset_id ? String(payload.dataset_id) : undefined,
                  queryQuestion: payload?.query_question ? String(payload.query_question) : question,
                  outputText: '',
                  cards: prev.caseSearch?.cards || [],
                  error: payload?.error ? String(payload.error) : payload?.message ? String(payload.message) : ''
                }
              };
            });
          },
          onDone: (result) => {
            setLoading(false);
            setPipeline((prev) => {
              const nextPipeline = {
                ...result,
                caseSearch: prev?.caseSearch || result.caseSearch
              };
              saveSnapshot(question, nextPipeline);
              setSavedFlag(true);
              return nextPipeline;
            });
            setStage('done');
            setNodeStageLabel('生成完成');
            message.success(`已生成 ${result.chapters.length} 个章节`);
          }
        }
      );
    } catch (error) {
      setStage('error');
      setNodeStageLabel('生成失败');
      const err = error instanceof Error ? error.message : '未知错误';
      message.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(mergedOutput);
    message.success('已复制全部章节结果');
  };

  const handleDownload = () => {
    downloadText('并行生成预案.md', mergedOutput);
  };

  const handleFillExample = () => {
    setQuestion(pickRandomPresetQuestion(enableMultiFaultSearch));
  };

  const renderPlanPage = () => (
    <div className="pipeline-page">
          <Card title="故障场景输入" className="panel-card pipeline-input-card">
            <TextArea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
              placeholder="请输入故障问题或场景，例如：暴雨导致电缆沟进水..."
            />
            <Space className="action-row" wrap>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={handleGenerate}>
                运行流水线
              </Button>
              <Button onClick={handleFillExample}>填入示例</Button>
              <Button size="small" icon={<CopyOutlined />} disabled={!chapters.length} onClick={handleCopy}>
                复制全部
              </Button>
              <Button size="small" icon={<DownloadOutlined />} disabled={!chapters.length} onClick={handleDownload}>
                下载全部
              </Button>
              <Checkbox
                className="action-toggle"
                checked={enableCaseSearch}
                onChange={(event) => setEnableCaseSearch(event.target.checked)}
              >
                开启案例搜索
              </Checkbox>
              <Checkbox
                className="action-toggle"
                checked={enableMultiFaultSearch}
                onChange={(event) => setEnableMultiFaultSearch(event.target.checked)}
              >
                开启多故障检索
              </Checkbox>
            </Space>
            <div className="status-box">
              <Tag color={stage === 'error' ? 'red' : stage === 'done' ? 'green' : 'processing'}>
                {stageText[stage]}
              </Tag>
              <Tag>{nodeStageLabel}</Tag>
              {savedFlag ? <Tag color="success">已保存</Tag> : null}
              {summaryTags.map((tag) => (
                <Tag color="purple" key={tag}>
                  {tag}
                </Tag>
              ))}
            </div>
          </Card>

          <div
            className="chapter-row"
            style={
              chapters.length
                ? {
                    gridTemplateColumns: showCompactLayout
                      ? 'repeat(3, minmax(0, 1fr))'
                      : `repeat(${chapters.length}, minmax(0, 1fr))`
                  }
                : undefined
            }
          >
            {chapters.length ? (
              chapters.map((chapter: PipelineChapter) => (
                <Card
                  key={`${chapter.chapterNo}-${chapter.title}`}
                  className="panel-card chapter-panel"
                  title={`${chapter.chapterNo} ${chapter.title}`}
                  extra={
                    <Tag color={chapter.status === 'done' ? 'green' : chapter.status === 'error' ? 'red' : 'processing'}>
                      {chapterStatusText[chapter.status]}
                    </Tag>
                  }
                >
                  <div className="chapter-meta">耗时：{chapter.elapsedSec ?? '-'}s · 小节数：{chapter.sectionCount}</div>
                  <Collapse
                    size="small"
                    className="chapter-collapse"
                    items={[
                      {
                        key: 'template',
                        label: '章节模板',
                        children: <div className="chapter-template-text">{chapter.templateText}</div>
                      }
                    ]}
                  />
                    <div className="chapter-panel__body">
                    {chapter.outputText ? (
                      <RichTextRenderer text={chapter.outputText} normalize={false} stripMeta showModeTags={showModeTags} />
                    ) : (
                      <Typography.Text type="secondary">本章节暂无输出。</Typography.Text>
                    )}
                  </div>
                </Card>
              ))
            ) : (
              <Card className="panel-card chapter-empty-card">
                <Typography.Text type="secondary">
                  运行后，每个章节会以一个独立竖向输出框显示在这里，并横向排列。
                </Typography.Text>
              </Card>
            )}
          </div>

          <Card title="案例检索" className="panel-card chapter-empty-card">
            {pipeline?.caseSearch?.enabled ? (
              pipeline.caseSearch.status === 'done' && caseCards.length > 0 ? (
                <>
                  <div className="chapter-meta">
                    知识库：{pipeline.caseSearch.kbName || '-'} · 查询：{pipeline.caseSearch.queryQuestion || '-'}
                  </div>
                  <div className="case-card-grid">
                    {caseCards.map((card, index) => (
                      <div className="case-search-card" key={`${card.id || index}-${card.title}`}>
                        <div className="case-search-card__header">
                          <Tag color="blue">命中 {index + 1}</Tag>
                        </div>
                        <div className="case-search-card__title">{card.title || '未命名案例'}</div>
                        <div className="case-search-card__meta-inline">
                          {card.kbId ? (
                            <span className="case-search-card__pill">
                              <span className="case-search-card__pill-label">知识库ID</span>
                              <span className="case-search-card__pill-value">{card.kbId}</span>
                            </span>
                          ) : null}
                          {card.docId ? (
                            <span className="case-search-card__pill">
                              <span className="case-search-card__pill-label">文档ID</span>
                              <span className="case-search-card__pill-value">{card.docId}</span>
                            </span>
                          ) : null}
                          {card.relevance ? (
                            <span className="case-search-card__pill case-search-card__pill--score">
                              <span className="case-search-card__pill-label">相关性</span>
                              <span className="case-search-card__pill-value">{card.relevance}</span>
                            </span>
                          ) : null}
                        </div>
                        <div className="case-search-card__excerpt">
                          {card.excerpt ? (
                            renderMarkedText(card.excerpt, { showModeTags })
                          ) : (
                            <Typography.Text type="secondary">无摘要</Typography.Text>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : pipeline.caseSearch.status === 'running' ? (
                <Typography.Text type="secondary">正在检索案例，请稍候。</Typography.Text>
              ) : pipeline.caseSearch.status === 'skipped' ? (
                <Typography.Text type="secondary">
                  未命中已建立知识库对应设备，已跳过案例检索。
                </Typography.Text>
              ) : pipeline.caseSearch.status === 'error' ? (
                <Typography.Text type="danger">
                  案例检索失败：{pipeline.caseSearch.error || '未知错误'}
                </Typography.Text>
              ) : (
                <Typography.Text type="secondary">等待开始案例检索。</Typography.Text>
              )
            ) : (
              <Typography.Text type="secondary">未开启案例搜索。</Typography.Text>
            )}
          </Card>
        </div>
  );

  return (
    <Layout className={`app-shell ${darkMode ? 'app-shell--dark' : ''}`}>
      <Header className="app-header">
        <div className="app-header__inner">
          <div>
            <Typography.Title level={3} className="app-title">
              电力设备智能预案生成系统
            </Typography.Title>
          </div>
          {authStatus === 'authenticated' ? (
            <div className="app-header__controls">
              <div className="app-user-bar">
                <div className="app-user-toggle">
                  <Typography.Text className="app-user-toggle__label">夜间模式</Typography.Text>
                  <Switch size="small" checked={darkMode} onChange={setDarkMode} />
                </div>
                <Tag color="blue">
                  当前用户：{currentUsername} · 用户组：{currentUserGroup}
                </Tag>
                <Button size="small" onClick={handleLogout}>
                  登出
                </Button>
              </div>
              <div className="app-route-bar">
                <div className="app-mode-toggle">
                  <div className="app-mode-toggle__item">
                    <Typography.Text className="app-mode-toggle__label">显示标签</Typography.Text>
                    <Switch size="small" checked={showModeTags} onChange={setShowModeTags} />
                  </div>
                  <div className="app-mode-toggle__item">
                    <Typography.Text className="app-mode-toggle__label">紧凑布局</Typography.Text>
                    <Switch size="small" checked={showCompactLayout} onChange={setShowCompactLayout} />
                  </div>
                </div>
                <div className="app-route-tabs">
                {routeItems.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`app-route-tab ${route === item.key ? 'app-route-tab--active' : ''}`}
                    onClick={() => navigateRoute(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </Header>
      <Content className="app-content">
        {authStatus === 'checking' ? (
          <Card className="panel-card chapter-empty-card auth-wait-card">
            <Typography.Text type="secondary">正在校验登录状态，请稍候。</Typography.Text>
          </Card>
        ) : null}
        {authStatus === 'unauthenticated' && route === 'login' ? (
          <LoginPage loading={loginLoading} errorMessage={loginErrorMessage} onSubmit={handleLogin} />
        ) : null}
        {authStatus === 'authenticated' && route === 'plan' ? renderPlanPage() : null}
        {authStatus === 'authenticated' && route === 'trace' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载图谱溯源页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <TraceGraphPage pipeline={pipeline} darkMode={darkMode} />
          </Suspense>
        ) : null}
        {authStatus === 'authenticated' && route === 'quality' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载格式优化与质量评估页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <QualityReviewPage
              currentUserGroup={currentUserGroup}
              showModeTags={showModeTags}
              compactLayout={showCompactLayout}
            />
          </Suspense>
        ) : null}
        {authStatus === 'authenticated' && route === 'template' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载模板查看页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <TemplateViewPage currentUserGroup={currentUserGroup} />
          </Suspense>
        ) : null}
      </Content>
    </Layout>
  );
}
