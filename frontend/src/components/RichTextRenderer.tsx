import type { ReactNode } from 'react';
import { Tag, Typography } from 'antd';

function renderInlineText(text: string, showModeTags: boolean): ReactNode[] {
  const parts = text.split(/(\[KG\]|\[GEN\]|\[FIX\]|\*\*[^*]+\*\*)/g);
  return parts
    .filter((part) => part !== '')
    .map((part, index) => {
      if (part === '[KG]') {
        if (!showModeTags) return null;
        return (
          <Tag color="blue" key={index}>
            KG
          </Tag>
        );
      }
      if (part === '[GEN]') {
        if (!showModeTags) return null;
        return (
          <Tag color="orange" key={index}>
            GEN
          </Tag>
        );
      }
      if (part === '[FIX]') {
        if (!showModeTags) return null;
        return (
          <Tag color="green" key={index}>
            FIX
          </Tag>
        );
      }
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return <span key={index}>{part}</span>;
    });
}

function normalizeRenderedOutput(text: string) {
  const raw = String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/([^\n])(#{1,4}\s+)/g, '$1\n$2')
    .replace(/([^\n])(第[一二三四五六七八九十0-9]+章)/g, '$1\n$2')
    .replace(/([^\n])(案例[一二三四五六七八九十百千0-9]+[：:\s])/g, '$1\n$2')
    .replace(/([^\n])(---+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\d+\s+)/g, '$1\n$2')
    .replace(/([^\n])(\d+\.\s+)/g, '$1\n$2')
    .replace(/([^\n])(内容来源：|图谱字段：|预定义文本：|生成要求：)/g, '$1\n$2');
  const headingPattern = /(^|\n)(#{1,4}\s+[^\n]+|第[一二三四五六七八九十0-9]+章[^\n]*)/m;
  const match = raw.match(headingPattern);

  if (!match || typeof match.index !== 'number') {
    return promoteStructuredHeadings(raw);
  }

  const startIndex = match[1] ? match.index + match[1].length : match.index;
  return promoteStructuredHeadings(raw.slice(startIndex).trimStart());
}

function cleanupInlineMetaLines(text: string) {
  const patterns = ['内容来源：', '图谱字段：', '预定义文本：', '生成要求：'];
  return text
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) return true;
      if (/^!\[.*\]\(.*\)$/.test(trimmed)) return false;
      if (/^\[图像内容省略\]$/.test(trimmed)) return false;
      return !patterns.some((marker) => trimmed.includes(marker));
    })
    .join('\n');
}

function promoteStructuredHeadings(text: string) {
  const lines = text.split('\n');
  const normalized: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    let line = lines[i].trim();

    if (!line) {
      normalized.push('');
      continue;
    }

    if (/^#{1,6}$/.test(line)) {
      continue;
    }

    if (/^GEN/.test(line)) {
      line = line.replace(/^GEN/, '').trim();
    } else if (/^KG/.test(line)) {
      line = line.replace(/^KG/, '').trim();
    } else if (/^FIX/.test(line)) {
      line = line.replace(/^FIX/, '').trim();
    }

    if (!line) {
      continue;
    }

    if (/^第[一二三四五六七八九十百千0-9]+章\s+.+$/.test(line)) {
      normalized.push(`# ${line}`);
      continue;
    }

    if (/^案例[一二三四五六七八九十百千0-9]+[：:\s].+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^\d+\.\d+\s+.+$/.test(line)) {
      normalized.push(`## ${line}`);
      continue;
    }

    if (/^\d+\.\s+.+$/.test(line)) {
      normalized.push(`### ${line}`);
      continue;
    }

    if (/^---+$/.test(line)) {
      normalized.push('');
      continue;
    }

    normalized.push(line);
  }

  return normalized.join('\n');
}

export function RichTextRenderer({
  text,
  normalize = true,
  stripMeta = true,
  emptyText = '暂无内容。',
  showModeTags = true
}: {
  text: string;
  normalize?: boolean;
  stripMeta?: boolean;
  emptyText?: string;
  showModeTags?: boolean;
}) {
  const rawText = normalize ? normalizeRenderedOutput(text) : String(text || '');
  const normalizedText = stripMeta ? cleanupInlineMetaLines(rawText) : rawText;

  if (!normalizedText.trim()) {
    return <Typography.Text type="secondary">{emptyText}</Typography.Text>;
  }

  return (
    <div className="rendered-rich-text">
      {normalizedText.split('\n').map((line, index) => {
        const trimmed = line.trim();

        if (!trimmed) {
          return <div className="render-blank" key={index} />;
        }

        if (trimmed.startsWith('#### ')) {
          return (
            <div className="render-h4" key={index}>
              {renderInlineText(trimmed.slice(5), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('### ')) {
          return (
            <div className="render-h3" key={index}>
              {renderInlineText(trimmed.slice(4), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('## ')) {
          return (
            <div className="render-h2" key={index}>
              {renderInlineText(trimmed.slice(3), showModeTags)}
            </div>
          );
        }

        if (trimmed.startsWith('# ')) {
          return (
            <div className="render-h1" key={index}>
              {renderInlineText(trimmed.slice(2), showModeTags)}
            </div>
          );
        }

        return (
          <div className="render-line" key={index}>
            {renderInlineText(line, showModeTags)}
          </div>
        );
      })}
    </div>
  );
}
