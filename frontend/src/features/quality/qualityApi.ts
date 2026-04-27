import type { PromptConfig } from './types';

async function readJsonSafely(response: Response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`响应不是有效 JSON：${text.slice(0, 160)}`);
  }
}

export async function fetchTemplatePrompts(): Promise<PromptConfig[]> {
  const response = await fetch('/api/template/prompts');
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return Array.isArray(data?.prompts) ? (data.prompts as PromptConfig[]) : [];
}

export async function saveTemplatePrompt(promptKey: string, promptText: string): Promise<PromptConfig> {
  const response = await fetch('/api/template/prompt/save', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      prompt_key: promptKey,
      prompt_text: promptText
    })
  });
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return data?.prompt as PromptConfig;
}
