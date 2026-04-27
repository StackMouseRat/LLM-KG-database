import { Button, Card, Input, Space, Tag, Typography } from 'antd';
import type { PromptConfig } from './types';

const { TextArea } = Input;

type QualityPromptPanelProps = {
  chaptersLength: number;
  promptLoading: boolean;
  prompts: PromptConfig[];
  canManagePrompts: boolean;
  editingPromptKey: string;
  promptDrafts: Record<string, string>;
  savingPromptKey: string;
  batchOptimizeLoading: boolean;
  batchRawEvaluateLoading: boolean;
  batchOptimizedEvaluateLoading: boolean;
  batchBusy: boolean;
  hasBatchRawEvaluableChapters: boolean;
  hasBatchOptimizedEvaluableChapters: boolean;
  onRunBatchReview: (target: 'optimize' | 'rawEvaluate' | 'optimizedEvaluate') => void;
  onBeginEditPrompt: (prompt: PromptConfig) => void;
  onCancelEditPrompt: () => void;
  onSavePrompt: (promptKey: string) => void;
  onLoadPrompts: (forceRefresh?: boolean) => void;
  onChangePromptDraft: (promptKey: string, value: string) => void;
};

export function QualityPromptPanel({
  chaptersLength,
  promptLoading,
  prompts,
  canManagePrompts,
  editingPromptKey,
  promptDrafts,
  savingPromptKey,
  batchOptimizeLoading,
  batchRawEvaluateLoading,
  batchOptimizedEvaluateLoading,
  batchBusy,
  hasBatchRawEvaluableChapters,
  hasBatchOptimizedEvaluableChapters,
  onRunBatchReview,
  onBeginEditPrompt,
  onCancelEditPrompt,
  onSavePrompt,
  onLoadPrompts,
  onChangePromptDraft
}: QualityPromptPanelProps) {
  return (
    <div className="quality-summary-grid">
      <Card title="格式优化与质量评估" className="panel-card">
        <Typography.Paragraph className="app-subtitle">
          当前页面支持对已生成预案按章节执行格式优化与质量评估，结果会流式展示；思考过程先展示 reasoning，随后自动切换为模型正式输出。顶部提示词支持缓存、编辑、保存和刷新。
        </Typography.Paragraph>
        <div className="quality-actions">
          <Space wrap>
            <Button
              type="primary"
              loading={batchOptimizeLoading}
              disabled={!chaptersLength || batchBusy}
              onClick={() => onRunBatchReview('optimize')}
            >
              全部优化
            </Button>
            <Button
              loading={batchRawEvaluateLoading}
              disabled={!hasBatchRawEvaluableChapters || batchBusy}
              onClick={() => onRunBatchReview('rawEvaluate')}
            >
              全部评估原文
            </Button>
            <Button
              loading={batchOptimizedEvaluateLoading}
              disabled={!hasBatchOptimizedEvaluableChapters || batchBusy}
              onClick={() => onRunBatchReview('optimizedEvaluate')}
            >
              全部评估优化后
            </Button>
          </Space>
        </div>
        <div className="status-box">
          <Tag color="blue">按章流式处理</Tag>
          <Tag>批量并发数 6</Tag>
          <Tag>{chaptersLength} 个章节</Tag>
          <Tag>{promptLoading ? '正在加载提示词' : `${prompts.length} 条提示词`}</Tag>
        </div>
      </Card>

      {['optimize_prompt', 'evaluate_prompt'].map((promptKey) => {
        const prompt = prompts.find((item) => item.prompt_key === promptKey);
        const editing = canManagePrompts && editingPromptKey === promptKey;
        return (
          <Card key={promptKey} title={prompt?.title || promptKey} className="panel-card">
            <div className="quality-actions">
              <Space wrap>
                {canManagePrompts ? (
                  !editing ? (
                    <Button size="small" onClick={() => prompt && onBeginEditPrompt(prompt)}>
                      编辑
                    </Button>
                  ) : (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        loading={savingPromptKey === promptKey}
                        onClick={() => onSavePrompt(promptKey)}
                      >
                        保存
                      </Button>
                      <Button size="small" onClick={onCancelEditPrompt}>
                        取消
                      </Button>
                    </>
                  )
                ) : null}
                <Button size="small" loading={promptLoading} onClick={() => onLoadPrompts(true)}>
                  刷新
                </Button>
              </Space>
            </div>
            {editing ? (
              <TextArea
                className="quality-prompt-editor"
                value={promptDrafts[promptKey] || ''}
                autoSize={false}
                onChange={(event) => onChangePromptDraft(promptKey, event.target.value)}
              />
            ) : (
              <div className="template-field__value template-field__value--long quality-prompt-preview">
                {prompt?.prompt_text || '暂无提示词内容。'}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
