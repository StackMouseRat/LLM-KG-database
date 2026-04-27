export type PromptConfig = {
  prompt_id: string;
  prompt_key: string;
  title: string;
  prompt_text: string;
  order_no: number;
  default?: {
    id?: string;
    prompt_key?: string;
    title?: string;
    prompt_text?: string;
    order_no?: number;
  };
};

export type ReviewStatus = 'idle' | 'started' | 'thinking' | 'generating' | 'done' | 'error';
export type LeftCardView = 'raw' | 'rawEvaluation' | 'optimizedEvaluation';
export type StreamTarget = 'optimize' | 'rawEvaluate' | 'optimizedEvaluate';

export type ReviewCache = {
  optimizeStatusMap: Record<string, ReviewStatus>;
  optimizeReasoningMap: Record<string, string>;
  optimizedMap: Record<string, string>;
  rawEvaluateStatusMap: Record<string, ReviewStatus>;
  rawEvaluateReasoningMap: Record<string, string>;
  rawEvaluationMap: Record<string, string>;
  optimizedEvaluateStatusMap: Record<string, ReviewStatus>;
  optimizedEvaluateReasoningMap: Record<string, string>;
  optimizedEvaluationMap: Record<string, string>;
  leftCardViewMap: Record<string, LeftCardView>;
};
