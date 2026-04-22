import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const PORT = Number(process.env.FRONTEND_PROXY_PORT || 8788);
const REPO_ROOT = process.env.LLM_KG_REPO_ROOT || '/home/ubuntu/LLM-KG-database';
const PIPELINE_SCRIPT =
  process.env.PIPELINE_SCRIPT ||
  path.join(REPO_ROOT, 'scripts', 'run_parallel_generation_pipeline.py');
const PIPELINE_RUN_DIR =
  process.env.PIPELINE_RUN_DIR ||
  path.join(REPO_ROOT, 'docs', 'project_changes', 'frontend_pipeline_runs');

function runPipeline(question) {
  return new Promise((resolve, reject) => {
    const baseDir = path.join(
      PIPELINE_RUN_DIR,
      `run_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
    );
    fs.mkdirSync(baseDir, { recursive: true });

    const child = spawn('python3', [PIPELINE_SCRIPT, '--question', question, '--output-dir', baseDir], {
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf-8');
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf-8');
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || stdout || `pipeline exited with code ${code}`));
        return;
      }

      const children = fs
        .readdirSync(baseDir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => path.join(baseDir, entry.name))
        .sort();

      const resultDir = children[children.length - 1];
      if (!resultDir) {
        reject(new Error(`pipeline result directory not found: ${baseDir}`));
        return;
      }

      const resultFile = path.join(resultDir, 'pipeline_result.json');
      if (!fs.existsSync(resultFile)) {
        reject(new Error(`pipeline result file not found: ${resultFile}`));
        return;
      }

      const raw = fs.readFileSync(resultFile, 'utf-8');
      resolve(JSON.parse(raw));
    });
  });
}

function sendSse(res, event, data) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf-8');
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    sendJson(res, 204, {});
    return;
  }

  if (
    req.method !== 'POST' ||
    (req.url !== '/api/plan/generate' && req.url !== '/api/pipeline/run')
  ) {
    sendJson(res, 404, { message: 'not found' });
    return;
  }

  try {
    const body = JSON.parse(await readBody(req));
    const question = String(body.question || '').trim();
    if (!question) {
      sendJson(res, 400, { message: 'question is required' });
      return;
    }
    const stream = Boolean(body.stream);

    if (!stream) {
      const result = await runPipeline(question);
      sendJson(res, 200, result);
      return;
    }

    const baseDir = path.join(
      PIPELINE_RUN_DIR,
      `run_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
    );
    fs.mkdirSync(baseDir, { recursive: true });

    const child = spawn(
      'python3',
      [PIPELINE_SCRIPT, '--question', question, '--output-dir', baseDir, '--stream-events'],
      {
        stdio: ['ignore', 'pipe', 'pipe']
      }
    );

    let stdoutBuffer = '';
    let stderr = '';

    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });

    child.stdout.on('data', (chunk) => {
      stdoutBuffer += chunk.toString('utf-8');
      const lines = stdoutBuffer.split('\n');
      stdoutBuffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const payload = JSON.parse(trimmed);
          if (payload?.event) {
            sendSse(res, payload.event, payload.data ?? {});
          }
        } catch {
          sendSse(res, 'pipeline_log', { text: trimmed });
        }
      }
    });

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf-8');
    });

    child.on('close', (code) => {
      if (stdoutBuffer.trim()) {
        try {
          const payload = JSON.parse(stdoutBuffer.trim());
          if (payload?.event) {
            sendSse(res, payload.event, payload.data ?? {});
          }
        } catch {
          sendSse(res, 'pipeline_log', { text: stdoutBuffer.trim() });
        }
      }

      if (code !== 0) {
        sendSse(res, 'pipeline_error', {
          message: stderr || `pipeline exited with code ${code}`
        });
      }

      sendSse(res, 'close', {});
      res.end();
    });
  } catch (error) {
    sendJson(res, 500, { message: error instanceof Error ? error.message : 'proxy error' });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`frontend proxy listening on ${PORT}`);
});
