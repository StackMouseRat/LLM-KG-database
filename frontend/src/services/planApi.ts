import type { GeneratePlanRequest, GeneratePlanResponse, StreamEventPayload, TraceNode } from '../types/plan';
import { parseTraceFromFastGPT } from '../utils/parseTrace';

function normalizeContent(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const record = item as Record<string, unknown>;
          if (typeof record.content === 'string') return record.content;
          if (typeof record.text === 'string') return record.text;
          if (record.text && typeof record.text === 'object') {
            return (record.text as Record<string, unknown>).content;
          }
        }
        return '';
      })
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

export async function generatePlan(payload: GeneratePlanRequest): Promise<GeneratePlanResponse> {
  const response = await fetch('/api/plan/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }

  const data = await response.json();
  const message = data?.choices?.[0]?.message;
  const answer = normalizeContent(message?.content);
  const trace = parseTraceFromFastGPT(data);

  return {
    answer,
    trace: {
      ...trace,
      graph: trace.graph ?? { nodes: [] as TraceNode[], edges: [] }
    },
    raw: data
  };
}

export async function generatePlanStream(
  payload: GeneratePlanRequest,
  handlers: {
    onStage?: (stage: string) => void;
    onAnswerChunk?: (text: string) => void;
    onDone?: (result: GeneratePlanResponse) => void;
  }
) {
  const response = await fetch('/api/plan/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify({ ...payload, stream: true })
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalRaw: any = null;
  let answer = '';

  const flushEvent = (rawChunk: string) => {
    const eventLine = rawChunk
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    let eventName = '';
    const dataLines: string[] = [];
    for (const line of eventLine) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }

    const payloadText = dataLines.join('\n');
    let payload: StreamEventPayload['data'] = payloadText;
    try {
      payload = JSON.parse(payloadText);
    } catch {
      payload = payloadText;
    }

    if (eventName === 'flowNodeStatus' && payload && typeof payload === 'object') {
      handlers.onStage?.((payload as any).name || '处理中');
      return;
    }

    if (eventName === 'answer' && payload && typeof payload === 'object') {
      const text = (payload as any).text || '';
      if (text) {
        answer += text;
        handlers.onAnswerChunk?.(answer);
      }
      return;
    }

    if (eventName === 'flowResponses') {
      finalRaw = payload;
      return;
    }

    if (eventName === 'close' && finalRaw) {
      const message = finalRaw?.choices?.[0]?.message;
      const content = normalizeContent(message?.content) || answer;
      const result: GeneratePlanResponse = {
        answer: content,
        trace: {
          ...parseTraceFromFastGPT(finalRaw),
          graph: parseTraceFromFastGPT(finalRaw).graph ?? { nodes: [], edges: [] }
        },
        raw: finalRaw
      };
      handlers.onDone?.(result);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      if (part.trim()) flushEvent(part);
    }
  }
}
