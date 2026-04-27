export type TemplateSection = {
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

export const SOURCE_TYPE_OPTIONS = ['KG', 'GEN', 'FIXED', 'KG+GEN', 'FIXED+GEN', 'REFGEN'];

export function normalizeSourceType(value: string) {
  return String(value || '').trim().toUpperCase();
}

export function toStoredSourceType(value: string) {
  const normalized = normalizeSourceType(value);
  return normalized === 'REFGEN' ? 'REFGEN' : normalized.toLowerCase();
}
