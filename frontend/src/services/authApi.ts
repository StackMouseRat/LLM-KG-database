export type AuthSession = {
  username: string;
  group: 'admin' | 'user';
};

export async function fetchCurrentUser(): Promise<AuthSession | null> {
  const response = await fetch('/api/auth/me', {
    method: 'GET',
    credentials: 'same-origin'
  });

  if (response.status === 401) {
    return null;
  }

  const data = await response.json();
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

  const data = await response.json();
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

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
}
