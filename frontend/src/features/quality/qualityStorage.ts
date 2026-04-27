import type { PipelineRunResponse } from '../../types/plan';
import type { PromptConfig, ReviewCache } from './types';

export const PLAN_SNAPSHOT_KEY = 'llmkg_saved_plan_snapshot_v1';
export const PROMPT_CACHE_KEY = 'llmkg_template_prompts_cache_v1';
export const REVIEW_CACHE_KEY = 'llmkg_quality_review_cache_v1';

export function loadSavedPipeline(): PipelineRunResponse | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PLAN_SNAPSHOT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.pipeline && typeof parsed.pipeline === 'object' ? (parsed.pipeline as PipelineRunResponse) : null;
  } catch {
    return null;
  }
}

export function loadPromptCache(): PromptConfig[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(PROMPT_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PromptConfig[]) : null;
  } catch {
    return null;
  }
}

export function savePromptCache(prompts: PromptConfig[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(PROMPT_CACHE_KEY, JSON.stringify(prompts));
}

export function loadReviewCache(): ReviewCache | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(REVIEW_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ReviewCache;
  } catch {
    return null;
  }
}

export function saveReviewCache(data: ReviewCache) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(REVIEW_CACHE_KEY, JSON.stringify(data));
}
