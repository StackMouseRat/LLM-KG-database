import type {
  PipelineRunRequest,
  PipelineRunResponse,
  PipelineChapter,
  PipelineCaseSearchResult,
  PipelineCaseSearchCard
} from '../types/plan';

function parseBasicInfo(raw: any) {
  const fields = raw?.basic_info?.fields || {};
  return {
    userQuestion: String(fields['用户问题'] || raw?.question || ''),
    faultScene: String(fields['故障与场景提取结果'] || ''),
    graphMaterial: String(fields['图谱检索方案素材'] || '')
  };
}

function parseTemplateSplit(raw: any) {
  const split = raw?.template_split?.split_result || {};
  return {
    templateId: String(split.template_id || ''),
    templateName: String(split.template_name || ''),
    currentVersion: String(split.current_version || ''),
    chapterCount: Number(split.chapter_count || 0)
  };
}

function parseChapters(raw: any): PipelineChapter[] {
  const chapters = raw?.parallel_generations;
  if (!Array.isArray(chapters)) return [];

  return chapters.map((chapter: any) => ({
    chapterNo: String(chapter.chapter_no || ''),
    title: String(chapter.title || ''),
    sectionCount: Number(chapter.section_count || 0),
    templateText: String(chapter.template_text || ''),
    outputText: String(chapter.output_text || ''),
    elapsedSec: typeof chapter.elapsed_sec === 'number' ? chapter.elapsed_sec : undefined,
    status: chapter.output_text ? 'done' : 'error'
  }));
}

function parseCaseSearch(raw: any): PipelineCaseSearchResult | undefined {
  const data = raw?.case_search;
  if (!data || typeof data !== 'object') return undefined;

  return {
    enabled: Boolean(data.enabled),
    status: String(data.status || 'idle') as PipelineCaseSearchResult['status'],
    kbName: data.kb_name ? String(data.kb_name) : undefined,
    datasetId: data.dataset_id ? String(data.dataset_id) : undefined,
    queryQuestion: data.query_question ? String(data.query_question) : undefined,
    outputText: data.output_text ? String(data.output_text) : undefined,
    cards: Array.isArray(data.cards)
      ? data.cards.map(
          (item: any): PipelineCaseSearchCard => ({
            id: item?.id ? String(item.id) : undefined,
            title: String(item?.title || '未命名案例'),
            kbId: String(item?.kbId || ''),
            docId: String(item?.docId || ''),
            relevance: String(item?.relevance || ''),
            excerpt: String(item?.excerpt || '')
          })
        )
      : undefined,
    error: data.error ? String(data.error) : undefined
  };
}

export async function runPipeline(payload: PipelineRunRequest): Promise<PipelineRunResponse> {
  const response = await fetch('/api/pipeline/run', {
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

  return {
    question: String(data?.question || payload.question),
    basicInfo: parseBasicInfo(data),
    templateSplit: parseTemplateSplit(data),
    chapters: parseChapters(data),
    caseSearch: parseCaseSearch(data),
    raw: data
  };
}

export async function runPipelineStream(
  payload: PipelineRunRequest,
  handlers: {
    onStage?: (stage: string, detail?: any) => void;
    onTemplateSplit?: (payload: any) => void;
    onChapterStarted?: (payload: any) => void;
    onChapterChunk?: (payload: any) => void;
    onChapterDone?: (payload: any) => void;
    onCaseSearchStarted?: (payload: any) => void;
    onCaseSearchDone?: (payload: any) => void;
    onCaseSearchError?: (payload: any) => void;
    onDone?: (result: PipelineRunResponse) => void;
  }
) {
  const response = await fetch('/api/pipeline/run', {
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

  const flushEvent = (rawChunk: string) => {
    const lines = rawChunk
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    let eventName = '';
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }

    let payloadData: any = {};
    const payloadText = dataLines.join('\n');
    if (payloadText) {
      try {
        payloadData = JSON.parse(payloadText);
      } catch {
        payloadData = payloadText;
      }
    }

    if (eventName === 'basic_info_started') {
      handlers.onStage?.('basic_info', payloadData);
      return;
    }
    if (eventName === 'basic_info_done') {
      handlers.onStage?.('basic_info', payloadData);
      return;
    }
    if (eventName === 'template_split_started') {
      handlers.onStage?.('template_split', payloadData);
      return;
    }
    if (eventName === 'template_split_done') {
      handlers.onStage?.('template_split', payloadData);
      handlers.onTemplateSplit?.(payloadData);
      return;
    }
    if (eventName === 'parallel_generating_started') {
      handlers.onStage?.('parallel_generating', payloadData);
      return;
    }
    if (eventName === 'chapter_started') {
      handlers.onChapterStarted?.(payloadData);
      return;
    }
    if (eventName === 'chapter_chunk') {
      handlers.onChapterChunk?.(payloadData);
      return;
    }
    if (eventName === 'chapter_done') {
      handlers.onChapterDone?.(payloadData);
      return;
    }
    if (eventName === 'case_search_started') {
      handlers.onStage?.('case_search', payloadData);
      handlers.onCaseSearchStarted?.(payloadData);
      return;
    }
    if (eventName === 'case_search_done') {
      handlers.onCaseSearchDone?.(payloadData);
      return;
    }
    if (eventName === 'case_search_error') {
      handlers.onCaseSearchError?.(payloadData);
      return;
    }
    if (eventName === 'pipeline_done') {
      const result = payloadData as PipelineRunResponse;
      handlers.onDone?.(result);
      return;
    }
    if (eventName === 'pipeline_error') {
      const message = payloadData?.message || '流水线执行失败';
      throw new Error(message);
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

  if (buffer.trim()) {
    flushEvent(buffer);
  }
}
