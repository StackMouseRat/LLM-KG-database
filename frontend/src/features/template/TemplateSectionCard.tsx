import { Button, Card, Input, Select, Space, Tag } from 'antd';
import type { TemplateSection } from './types';
import { normalizeSourceType, SOURCE_TYPE_OPTIONS } from './types';

const { TextArea } = Input;

type TemplateSectionCardProps = {
  section: TemplateSection;
  draft: TemplateSection;
  editing: boolean;
  canManageTemplate: boolean;
  saving: boolean;
  onBeginEdit: (section: TemplateSection) => void;
  onCancelEdit: () => void;
  onUpdateDraft: (sectionId: string, patch: Partial<TemplateSection>) => void;
  onSaveSection: (sectionId: string) => void;
  onResetSection: (sectionId: string) => void;
};

export function TemplateSectionCard({
  section,
  draft,
  editing,
  canManageTemplate,
  saving,
  onBeginEdit,
  onCancelEdit,
  onUpdateDraft,
  onSaveSection,
  onResetSection
}: TemplateSectionCardProps) {
  return (
    <Card
      key={section.section_id}
      className="panel-card template-card"
      title={`${section.section_no} ${section.title}`}
      extra={<Tag color="blue">L{section.level}</Tag>}
    >
      <div className="template-card__meta">
        <Tag color="purple">{normalizeSourceType(section.source_type) || '未设置'}</Tag>
        {section.kg_field ? <Tag color="cyan">{section.kg_field}</Tag> : null}
      </div>

      <div className="template-card__body">
        <div className="template-field">
          <div className="template-field__label">source_type</div>
          {editing ? (
            <Select
              value={normalizeSourceType(draft.source_type)}
              options={SOURCE_TYPE_OPTIONS.map((item) => ({ value: item, label: item }))}
              onChange={(value) => onUpdateDraft(section.section_id, { source_type: value })}
            />
          ) : (
            <div className="template-field__value">{normalizeSourceType(section.source_type) || '-'}</div>
          )}
        </div>

        <div className="template-field">
          <div className="template-field__label">fixed_text</div>
          {editing ? (
            <TextArea
              value={draft.fixed_text}
              autoSize={{ minRows: 4, maxRows: 8 }}
              onChange={(event) => onUpdateDraft(section.section_id, { fixed_text: event.target.value })}
            />
          ) : (
            <div className="template-field__value template-field__value--long">{section.fixed_text || '-'}</div>
          )}
        </div>

        <div className="template-field">
          <div className="template-field__label">gen_instruction</div>
          {editing ? (
            <TextArea
              value={draft.gen_instruction}
              autoSize={{ minRows: 4, maxRows: 8 }}
              onChange={(event) => onUpdateDraft(section.section_id, { gen_instruction: event.target.value })}
            />
          ) : (
            <div className="template-field__value template-field__value--long">{section.gen_instruction || '-'}</div>
          )}
        </div>
      </div>

      {canManageTemplate ? (
        <Space className="template-card__actions" wrap>
          {!editing ? (
            <Button onClick={() => onBeginEdit(section)}>编辑</Button>
          ) : (
            <>
              <Button type="primary" loading={saving} onClick={() => onSaveSection(section.section_id)}>
                保存
              </Button>
              <Button onClick={onCancelEdit}>取消</Button>
            </>
          )}
          <Button danger loading={saving} onClick={() => onResetSection(section.section_id)}>
            恢复默认
          </Button>
        </Space>
      ) : null}
    </Card>
  );
}
