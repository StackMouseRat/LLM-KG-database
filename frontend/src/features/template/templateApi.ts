import type { TemplateSection } from './types';
import { toStoredSourceType } from './types';

async function readJsonSafely(response: Response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`响应不是有效 JSON：${text.slice(0, 160)}`);
  }
}

export async function fetchTemplateSections(): Promise<TemplateSection[]> {
  const response = await fetch('/api/template/sections');
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return Array.isArray(data?.sections) ? data.sections : [];
}

export async function saveTemplateSection(sectionId: string, draft: TemplateSection): Promise<TemplateSection> {
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
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.section as TemplateSection;
}

export async function resetTemplateSection(sectionId: string): Promise<TemplateSection> {
  const response = await fetch('/api/template/section/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ section_id: sectionId })
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.section as TemplateSection;
}
