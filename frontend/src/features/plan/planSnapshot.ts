import type { PipelineRunResponse } from '../../types/plan';

export const PLAN_SNAPSHOT_KEY = 'llmkg_saved_plan_snapshot_v1';

export function loadSavedSnapshot(): { question: string; pipeline: PipelineRunResponse } | null {
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

export function saveSnapshot(question: string, pipeline: PipelineRunResponse) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(
    PLAN_SNAPSHOT_KEY,
    JSON.stringify({
      question,
      pipeline
    })
  );
}
