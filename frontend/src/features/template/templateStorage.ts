import type { TemplateSection } from './types';

export const TEMPLATE_CACHE_KEY = 'llmkg_template_sections_cache_v1';

export function loadTemplateCache(): TemplateSection[] | null {
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

export function saveTemplateCache(sections: TemplateSection[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(TEMPLATE_CACHE_KEY, JSON.stringify(sections));
}
