import type { TemplateSection } from './types';
import { toStoredSourceType } from './types';

export async function fetchTemplateSections(): Promise<TemplateSection[]> {
  const response = await fetch('/api/template/sections');
  const data = await response.json();
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
  const data = await response.json();
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
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.section as TemplateSection;
}
