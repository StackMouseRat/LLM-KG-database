import { useMemo, useState } from 'react';
import { Button, Card, Input, Layout, message, Space, Tabs, Tag, Typography } from 'antd';
import { CopyOutlined, DownloadOutlined, PlayCircleOutlined, SearchOutlined } from '@ant-design/icons';
import type { GeneratePlanResponse, GenerateStage } from './types/plan';
import { generatePlanStream } from './services/planApi';
import { downloadText } from './utils/download';
import { TraceGraphPage } from './pages/TraceGraphPage';

const { Header, Content } = Layout;
const { TextArea } = Input;

const demoQuestion =
  '暴雨导致电缆沟进水，开关柜出现绝缘告警，夜间值班，无法立即更换设备，需要一份简短的双阶段处置方案。';

const stageText: Record<GenerateStage, string> = {
  idle: '等待输入',
  detecting_device: '正在识别设备',
  querying_graph: '正在查询知识图谱',
  generating: '正在生成预案',
  done: '生成完成',
  error: '生成失败'
};

function renderMarkedText(text: string) {
  const parts = text.split(/(\[KG\]|\[GEN\])/g);
  return parts.map((part, index) => {
    if (part === '[KG]') {
      return <Tag color="blue" key={index}>KG</Tag>;
    }
    if (part === '[GEN]') {
      return <Tag color="orange" key={index}>GEN</Tag>;
    }
    return <span key={index}>{part}</span>;
  });
}

export default function App() {
  const [question, setQuestion] = useState(demoQuestion);
  const [answer, setAnswer] = useState('');
  const [trace, setTrace] = useState<GeneratePlanResponse['trace'] | null>(null);
  const [stage, setStage] = useState<GenerateStage>('idle');
  const [nodeStageLabel, setNodeStageLabel] = useState('等待输入');
  const [activeTab, setActiveTab] = useState('generate');
  const [loading, setLoading] = useState(false);

  const canShowTrace = useMemo(() => !!trace?.graph.nodes.length, [trace]);

  const handleGenerate = async () => {
    if (!question.trim()) {
      message.warning('请先输入故障场景描述');
      return;
    }
    setLoading(true);
    setAnswer('');
    setTrace(null);
    setStage('detecting_device');
    setNodeStageLabel('正在识别设备');
    try {
      await generatePlanStream(
        { question },
        {
          onStage: (name) => {
            setNodeStageLabel(name);
            if (['设备识别', '获取全体设备表', '清洗设备表数据'].includes(name)) {
              setStage('detecting_device');
            } else if (['基础数据获取', '基础数据清洗', '故障类型分析', '下游节点获取', '下游节点数据清洗'].includes(name)) {
              setStage('querying_graph');
            } else {
              setStage('generating');
            }
          },
          onAnswerChunk: (text) => {
            setAnswer(text);
          },
          onDone: (result) => {
            setAnswer(result.answer);
            setTrace(result.trace);
            setStage('done');
            setNodeStageLabel('生成完成');
          }
        }
      );
      message.success('预案生成完成');
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
    await navigator.clipboard.writeText(answer);
    message.success('已复制到剪贴板');
  };

  const handleDownload = () => {
    downloadText('应急预案.md', answer);
  };

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <div>
          <Typography.Title level={3} className="app-title">
            电力设备应急预案生成系统
          </Typography.Title>
          <Typography.Text className="app-subtitle">场景化预案生成 · 知识图谱溯源</Typography.Text>
        </div>
      </Header>
      <Content className="app-content">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'generate',
              label: '预案生成',
              children: (
                <div className="generate-grid">
                  <Card title="故障场景输入" className="panel-card">
                    <TextArea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      autoSize={{ minRows: 8, maxRows: 12 }}
                      placeholder="请描述故障场景，例如：暴雨导致电缆沟进水..."
                    />
                    <Space className="action-row" wrap>
                      <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={handleGenerate}>
                        生成预案
                      </Button>
                      <Button onClick={() => setQuestion(demoQuestion)}>填入示例</Button>
                    </Space>
                    <div className="status-box">
                      <Tag color={stage === 'error' ? 'red' : stage === 'done' ? 'green' : 'processing'}>
                        {stageText[stage]}
                      </Tag>
                      <Tag>{nodeStageLabel}</Tag>
                      {trace?.device && <Tag>{trace.device}</Tag>}
                      {trace?.fault && <Tag color="purple">{trace.fault}</Tag>}
                    </div>
                  </Card>

                  <Card
                    title="生成结果"
                    className="panel-card result-card"
                    extra={
                      <Space>
                        <Button size="small" icon={<CopyOutlined />} disabled={!answer} onClick={handleCopy}>
                          复制
                        </Button>
                        <Button size="small" icon={<DownloadOutlined />} disabled={!answer} onClick={handleDownload}>
                          下载
                        </Button>
                        <Button
                          size="small"
                          icon={<SearchOutlined />}
                          disabled={!canShowTrace}
                          onClick={() => setActiveTab('trace')}
                        >
                          查看溯源
                        </Button>
                      </Space>
                    }
                  >
                    <div className="result-content">
                      {answer ? renderMarkedText(answer) : <Typography.Text type="secondary">生成结果将在这里显示。</Typography.Text>}
                    </div>
                  </Card>
                </div>
              )
            },
            {
              key: 'trace',
              label: '溯源分析',
              children: <TraceGraphPage trace={trace} />
            }
          ]}
        />
      </Content>
    </Layout>
  );
}
