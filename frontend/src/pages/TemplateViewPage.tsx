import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Empty, Input, Select, Space, Tag, Typography, message } from 'antd';

const { TextArea } = Input;
const TEMPLATE_CACHE_KEY = 'llmkg_template_sections_cache_v1';

type TemplateSection = {
  section_id: string;
  section_no: string;
  title: string;
  level: number;
  order_no: number;
  source_type: string;
  kg_field?: string;
  fixed_text?: string;
  gen_instruction?: string;
  default?: {
    source_type?: string;
    fixed_text?: string;
    gen_instruction?: string;
  };
};

const SOURCE_TYPE_OPTIONS = ['KG', 'GEN', 'FIXED', 'KG+GEN', 'FIXED+GEN', 'REFGEN'];

function normalizeSourceType(value: string) {
  return String(value || '').trim().toUpperCase();
}

function toStoredSourceType(value: string) {
  const normalized = normalizeSourceType(value);
  return normalized === 'REFGEN' ? 'REFGEN' : normalized.toLowerCase();
}

function loadTemplateCache(): TemplateSection[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(TEMPLATE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as TemplateSection[]) : null;
  } catch {
    return null;
  }
}

function saveTemplateCache(sections: TemplateSection[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(TEMPLATE_CACHE_KEY, JSON.stringify(sections));
}

export function TemplateViewPage({ currentUserGroup }: { currentUserGroup: 'admin' | 'user' }) {
  const [sections, setSections] = useState<TemplateSection[]>(() => loadTemplateCache() || []);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState('');
  const [editingId, setEditingId] = useState('');
  const [drafts, setDrafts] = useState<Record<string, TemplateSection>>({});

  const canManageTemplate = currentUserGroup === 'admin';

  const loadSections = async (forceRefresh = false) => {
    if (!forceRefresh) {
      const cached = loadTemplateCache();
      if (cached?.length) {
        setSections(cached);
        return;
      }
    }
    setLoading(true);
    try {
      const response = await fetch('/api/template/sections');
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || `请求失败：${response.status}`);
      }
      const items = Array.isArray(data?.sections) ? data.sections : [];
      setSections(items);
      saveTemplateCache(items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '模板章节加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSections();
  }, []);

  const sortedSections = useMemo(
    () => [...sections].sort((a, b) => Number(a.order_no || 0) - Number(b.order_no || 0)),
    [sections]
  );

  const beginEdit = (section: TemplateSection) => {
    setEditingId(section.section_id);
    setDrafts((prev) => ({
      ...prev,
      [section.section_id]: { ...section }
    }));
  };

  const cancelEdit = () => {
    setEditingId('');
  };

  const updateDraft = (sectionId: string, patch: Partial<TemplateSection>) => {
    setDrafts((prev) => ({
      ...prev,
      [sectionId]: {
        ...prev[sectionId],
        ...patch
      }
    }));
  };

  const saveSection = async (sectionId: string) => {
    const draft = drafts[sectionId];
    if (!draft) return;
    setSavingId(sectionId);
    try {
      const response = await fetch('/api/template/section/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          section_id: sectionId,
          source_type: toStoredSourceType(draft.source_type || ''),
          fixed_text: draft.fixed_text || '',
          gen_instruction: draft.gen_instruction || ''
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || `请求失败：${response.status}`);
      }
      const updated = data?.section as TemplateSection;
      setSections((prev) => {
        const next = prev.map((item) => (item.section_id === sectionId ? updated : item));
        saveTemplateCache(next);
        return next;
      });
      setEditingId('');
      message.success(`已保存章节 ${updated?.section_no || sectionId}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSavingId('');
    }
  };

  const resetSection = async (sectionId: string) => {
    setSavingId(sectionId);
    try {
      const response = await fetch('/api/template/section/reset', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ section_id: sectionId })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || `请求失败：${response.status}`);
      }
      const updated = data?.section as TemplateSection;
      setSections((prev) => {
        const next = prev.map((item) => (item.section_id === sectionId ? updated : item));
        saveTemplateCache(next);
        return next;
      });
      setDrafts((prev) => ({
        ...prev,
        [sectionId]: { ...updated }
      }));
      setEditingId('');
      message.success(`已恢复默认：${updated?.section_no || sectionId}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '恢复默认失败');
    } finally {
      setSavingId('');
    }
  };

  return (
    <div className="pipeline-page">
      <Card title="模板查看" className="panel-card pipeline-input-card">
        <Typography.Paragraph className="app-subtitle">
          当前页用于查看模板章节。
          {canManageTemplate
            ? ' 每个章节卡片可独立修改 `source_type`、`fixed_text` 和 `gen_instruction`，并可保存到数据库或恢复为当前默认值。'
            : ' 当前账号为只读权限，可查看模板内容但不能编辑或恢复默认。'}
        </Typography.Paragraph>
        <div className="status-box">
          <Tag color="cyan">模板定制</Tag>
          <Tag>{loading ? '正在加载模板章节' : `${sortedSections.length} 个章节`}</Tag>
        </div>
        <Space className="action-row" wrap>
          <Button loading={loading} onClick={() => loadSections(true)}>
            刷新模板
          </Button>
        </Space>
      </Card>

      {sortedSections.length ? (
        <div className="template-card-grid">
          {sortedSections.map((section) => {
            const editing = editingId === section.section_id;
            const draft = drafts[section.section_id] || section;
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
                        onChange={(value) => updateDraft(section.section_id, { source_type: value })}
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
                        onChange={(event) =>
                          updateDraft(section.section_id, { fixed_text: event.target.value })
                        }
                      />
                    ) : (
                      <div className="template-field__value template-field__value--long">
                        {section.fixed_text || '-'}
                      </div>
                    )}
                  </div>

                  <div className="template-field">
                    <div className="template-field__label">gen_instruction</div>
                    {editing ? (
                      <TextArea
                        value={draft.gen_instruction}
                        autoSize={{ minRows: 4, maxRows: 8 }}
                        onChange={(event) =>
                          updateDraft(section.section_id, { gen_instruction: event.target.value })
                        }
                      />
                    ) : (
                      <div className="template-field__value template-field__value--long">
                        {section.gen_instruction || '-'}
                      </div>
                    )}
                  </div>
                </div>

                {canManageTemplate ? (
                  <Space className="template-card__actions" wrap>
                    {!editing ? (
                      <Button onClick={() => beginEdit(section)}>编辑</Button>
                    ) : (
                      <>
                        <Button
                          type="primary"
                          loading={savingId === section.section_id}
                          onClick={() => saveSection(section.section_id)}
                        >
                          保存
                        </Button>
                        <Button onClick={cancelEdit}>取消</Button>
                      </>
                    )}
                    <Button
                      danger
                      loading={savingId === section.section_id}
                      onClick={() => resetSection(section.section_id)}
                    >
                      恢复默认
                    </Button>
                  </Space>
                ) : null}
              </Card>
            );
          })}
        </div>
      ) : (
        <Card className="panel-card chapter-empty-card">
          <Empty description={loading ? '正在加载模板章节...' : '暂无模板章节数据'} />
        </Card>
      )}
    </div>
  );
}
