import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { ALL_MULTI_FAULT_QUESTIONS, ALL_SINGLE_FAULT_QUESTIONS, EXPERIMENT_QUESTION_GROUPS } from '../data/presetQuestions';

const { Paragraph, Text, Title } = Typography;

const experimentPlans = [
  {
    title: '输入边界实验',
    tag: '边界',
    questionSource: '无关类、错配类、不支持设备输入',
    comparison: '旧链路直接生成 vs 当前边界校验终止',
    metrics: ['终止准确率', '提示可读性', '伪预案避免率']
  },
  {
    title: '设备主体消歧实验',
    tag: '消歧',
    questionSource: '混淆类问题',
    comparison: '直接生成 vs 基本信息获取 + 图谱检索',
    metrics: ['设备识别正确率', '知识库命中率', '故障二级节点准确率']
  },
  {
    title: '图谱增强实验',
    tag: '图谱',
    questionSource: '图谱依赖类问题',
    comparison: '不传图谱素材 vs 当前完整链路',
    metrics: ['原因覆盖度', '措施覆盖度', '风险资源覆盖度']
  },
  {
    title: '模板结构实验',
    tag: '模板',
    questionSource: '模板结构类问题',
    comparison: '自由生成整篇 vs 模板切片并行生成',
    metrics: ['章节完整率', '标题一致性', '章节边界稳定性']
  },
  {
    title: '多故障链式实验',
    tag: '链式',
    questionSource: '多故障链式类问题',
    comparison: '普通单故障链路 vs 多故障识别 + 逐故障图谱查询',
    metrics: ['故障拆解率', '主次识别正确率', '融合处置完整度']
  },
  {
    title: '场景约束传播实验',
    tag: '约束',
    questionSource: '场景约束类、不全类问题',
    comparison: '直接生成 vs 当前完整链路',
    metrics: ['约束保留率', '排查路径完整度', '冲突措施避免率']
  }
];

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

      <Row gutter={[16, 16]}>
        {experimentPlans.map((plan) => (
          <Col xs={24} lg={12} xl={8} key={plan.title}>
            <Card className="panel-card experiment-plan-card" title={plan.title} extra={<Tag color="purple">{plan.tag}</Tag>}>
              <Space direction="vertical" size={10}>
                <div>
                  <Text strong>题集来源</Text>
                  <Paragraph className="experiment-plan-card__text">{plan.questionSource}</Paragraph>
                </div>
                <div>
                  <Text strong>对比方式</Text>
                  <Paragraph className="experiment-plan-card__text">{plan.comparison}</Paragraph>
                </div>
                <div>
                  <Text strong>核心指标</Text>
                  <div className="experiment-plan-card__metrics">
                    {plan.metrics.map((metric) => (
                      <Tag key={metric}>{metric}</Tag>
                    ))}
                  </div>
                </div>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
