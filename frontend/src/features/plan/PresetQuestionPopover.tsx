import { Typography } from 'antd';
import { DEVICE_QUESTIONS, EXPERIMENT_QUESTION_GROUPS } from '../../data/presetQuestions';

type PresetQuestionPopoverProps = {
  onPickQuestion: (question: string) => void;
};

export function PresetQuestionPopover({ onPickQuestion }: PresetQuestionPopoverProps) {
  const { Text, Title } = Typography;

  return (
    <div className="preset-popover__content">
      <div className="preset-popover__group preset-popover__group--single">
        <div className="preset-popover__heading">
          <span className="preset-popover__badge preset-popover__badge--single">单故障</span>
          <div className="preset-popover__heading-copy">
            <Title level={5} className="preset-popover__title">常规单故障问题</Title>
            <Typography.Text className="preset-popover__desc">适合单一主故障场景，生成链路更直接。</Typography.Text>
          </div>
        </div>
        {DEVICE_QUESTIONS.map((device) => (
          <div key={`single-${device.device}`} className="preset-popover__section">
            <Text strong className="preset-popover__device preset-popover__device--single">{device.device}</Text>
            {device.singleFault.map((question, index) => (
              <div
                key={index}
                className="preset-item"
                onClick={() => onPickQuestion(question)}
              >
                {question.length > 60 ? `${question.substring(0, 60)}…` : question}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="preset-popover__group preset-popover__group--multi">
        <div className="preset-popover__heading">
          <span className="preset-popover__badge preset-popover__badge--multi">多故障</span>
          <div className="preset-popover__heading-copy">
            <Title level={5} className="preset-popover__title">常规多故障问题</Title>
            <Typography.Text className="preset-popover__desc">适合并发或伴随故障场景，会触发多故障检索思路。</Typography.Text>
          </div>
        </div>
        {DEVICE_QUESTIONS.map((device) => (
          <div key={`multi-${device.device}`} className="preset-popover__section">
            <Text strong className="preset-popover__device preset-popover__device--multi">{device.device}</Text>
            {device.multiFault.map((question, index) => (
              <div
                key={index}
                className="preset-item"
                onClick={() => onPickQuestion(question)}
              >
                {question.length > 60 ? `${question.substring(0, 60)}…` : question}
              </div>
            ))}
          </div>
        ))}
      </div>
      {EXPERIMENT_QUESTION_GROUPS.map((group, groupIndex) => (
        <div
          key={group.key}
          className={`preset-popover__group ${groupIndex % 2 === 0 ? 'preset-popover__group--single' : 'preset-popover__group--multi'}`}
        >
          <div className="preset-popover__heading">
            <span
              className={`preset-popover__badge ${groupIndex % 2 === 0 ? 'preset-popover__badge--single' : 'preset-popover__badge--multi'}`}
            >
              {group.badge}
            </span>
            <div className="preset-popover__heading-copy">
              <Title level={5} className="preset-popover__title">{group.title}</Title>
              <Typography.Text className="preset-popover__desc">{group.description}</Typography.Text>
            </div>
          </div>
          <div className="preset-popover__section">
            <Text
              strong
              className={`preset-popover__device ${groupIndex % 2 === 0 ? 'preset-popover__device--single' : 'preset-popover__device--multi'}`}
            >
              实验备用题
            </Text>
            {group.questions.map((question, index) => (
              <div key={index} className="preset-item" onClick={() => onPickQuestion(question)}>
                {question.length > 60 ? `${question.substring(0, 60)}…` : question}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
