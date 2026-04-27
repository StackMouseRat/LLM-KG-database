export type AuthSession = {
  username: string;
  group: 'admin' | 'user';
};

async function readJsonSafely(response: Response) {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`响应不是有效 JSON：${text.slice(0, 160)}`);
  }
}

export async function fetchCurrentUser(): Promise<AuthSession | null> {
  const response = await fetch('/api/auth/me', {
    method: 'GET',
    credentials: 'same-origin'
  });

  if (response.status === 401) {
    return null;
  }

  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }

  return {
    username: String(data?.username || ''),
    group: (String(data?.group || 'user') === 'admin' ? 'admin' : 'user') as AuthSession['group']
  };
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      username,
      password
    })
  });

  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }

  return {
    username: String(data?.username || username),
    group: (String(data?.group || 'user') === 'admin' ? 'admin' : 'user') as AuthSession['group']
  };
}

export async function logout() {
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'same-origin'
  });

  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
}
