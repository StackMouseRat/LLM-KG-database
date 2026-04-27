import { Typography } from 'antd';
import type { ExperimentQuestionSuite } from './experimentApi';


export function ExperimentQuestionPopover({ suite }: { suite: ExperimentQuestionSuite }) {
  const { Text, Title } = Typography;

  return (
    <div className="preset-popover__content">
      {suite.groups.map((group, groupIndex) => (
        <div
          key={group.groupId}
          className={`preset-popover__group ${groupIndex % 2 === 0 ? 'preset-popover__group--single' : 'preset-popover__group--multi'}`}
        >
          <div className="preset-popover__heading">
            <span className={`preset-popover__badge ${groupIndex % 2 === 0 ? 'preset-popover__badge--single' : 'preset-popover__badge--multi'}`}>
              {group.code} 组
            </span>
            <div className="preset-popover__heading-copy">
              <Title level={5} className="preset-popover__title">{group.name}</Title>
              <Typography.Text className="preset-popover__desc">{group.purpose}</Typography.Text>
            </div>
          </div>
          <div className="preset-popover__section">
            <Text strong className={`preset-popover__device ${groupIndex % 2 === 0 ? 'preset-popover__device--single' : 'preset-popover__device--multi'}`}>
              {group.questions.length} 条问题
            </Text>
            {group.questions.map((question) => (
              <div key={question.questionId} className="preset-item">
                {question.questionText}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
