import http from 'node:http';
import fs from 'node:fs';

const PORT = Number(process.env.FRONTEND_PROXY_PORT || 8788);
const FASTGPT_URL = process.env.FASTGPT_CHAT_URL || 'http://127.0.0.1:3000/api/v1/chat/completions';
const KEY_FILE = process.env.FASTGPT_API_KEY_FILE || '/home/ubuntu/.fastgpt_keys/app_api_key_c_class';

function readApiKey() {
  return fs.readFileSync(KEY_FILE, 'utf-8').trim();
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

  if (req.url !== '/api/plan/generate' || req.method !== 'POST') {
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
    const upstreamPayload = {
      chatId: `frontend-${Date.now()}`,
      stream,
      detail: true,
      messages: [{ role: 'user', content: question }],
      customUid: 'frontend-demo'
    };

    const upstream = await fetch(FASTGPT_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${readApiKey()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(upstreamPayload)
    });

    if (stream) {
      res.writeHead(upstream.status, {
        'Content-Type': upstream.headers.get('content-type') || 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'Access-Control-Allow-Origin': '*'
      });
      if (upstream.body) {
        for await (const chunk of upstream.body) {
          res.write(chunk);
        }
      }
      res.end();
      return;
    }

    const text = await upstream.text();
    res.writeHead(upstream.status, {
      'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*'
    });
    res.end(text);
  } catch (error) {
    sendJson(res, 500, { message: error instanceof Error ? error.message : 'proxy error' });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`frontend proxy listening on ${PORT}`);
});
