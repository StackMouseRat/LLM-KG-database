import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Empty, Space, Tag, Typography, message } from 'antd';
import { TemplateSectionCard } from '../features/template/TemplateSectionCard';
import { fetchTemplateSections, resetTemplateSection, saveTemplateSection } from '../features/template/templateApi';
import { loadTemplateCache, saveTemplateCache } from '../features/template/templateStorage';
import type { TemplateSection } from '../features/template/types';

export function TemplateViewPage({
  currentUserGroup,
  compactLayout
}: {
  currentUserGroup: 'admin' | 'user';
  compactLayout: boolean;
}) {
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
      const items = await fetchTemplateSections();
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
      const updated = await saveTemplateSection(sectionId, draft);
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
      const updated = await resetTemplateSection(sectionId);
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
        <div className={`template-card-grid ${compactLayout ? 'template-card-grid--compact' : ''}`}>
          {sortedSections.map((section) => {
            const editing = editingId === section.section_id;
            const draft = drafts[section.section_id] || section;
            return (
              <TemplateSectionCard
                key={section.section_id}
                section={section}
                draft={draft}
                editing={editing}
                canManageTemplate={canManageTemplate}
                saving={savingId === section.section_id}
                onBeginEdit={beginEdit}
                onCancelEdit={cancelEdit}
                onUpdateDraft={updateDraft}
                onSaveSection={(sectionId) => void saveSection(sectionId)}
                onResetSection={(sectionId) => void resetSection(sectionId)}
              />
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
