import type { PipelineRunResponse, PlanTrace } from '../../types/plan';

const TRACE_CACHE_KEY = 'llmkg_trace_subgraph_cache_v1';

type TraceCachePayload = {
  signature: string;
  trace: PlanTrace;
  animationPlayed: boolean;
  viewport?: TraceViewport;
};

export type TraceViewport = {
  zoom: number;
  position: [number, number];
  rotation?: number;
};

export function buildTraceCacheSignature(pipeline: PipelineRunResponse | null) {
  if (!pipeline) return '';
  return JSON.stringify({
    question: pipeline.question || '',
    faultScene: pipeline.basicInfo?.faultScene || '',
    graphMaterial: pipeline.basicInfo?.graphMaterial || '',
    chapters: (pipeline.chapters || []).map((chapter) => ({
      chapterNo: chapter.chapterNo,
      title: chapter.title,
      outputText: chapter.outputText
    }))
  });
}

export function loadTraceCache(signature: string): TraceCachePayload | null {
  if (!signature || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(TRACE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TraceCachePayload;
    if (parsed?.signature !== signature || !parsed.trace?.graph) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveTraceCache(signature: string, trace: PlanTrace, animationPlayed: boolean, viewport?: TraceViewport) {
  if (!signature || typeof window === 'undefined') return;
  window.localStorage.setItem(
    TRACE_CACHE_KEY,
    JSON.stringify({
      signature,
      trace,
      animationPlayed,
      viewport
    } satisfies TraceCachePayload)
  );
}

export function markTraceAnimationPlayed(signature: string) {
  const cached = loadTraceCache(signature);
  if (!cached) return;
  saveTraceCache(signature, cached.trace, true, cached.viewport);
}

export function saveTraceViewport(signature: string, viewport: TraceViewport) {
  const cached = loadTraceCache(signature);
  if (!cached) return;
  saveTraceCache(signature, cached.trace, cached.animationPlayed, viewport);
}
