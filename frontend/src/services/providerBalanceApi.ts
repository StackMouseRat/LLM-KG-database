export type ProviderBalance = {
  id: string;
  name: string;
  ok: boolean;
  available?: boolean;
  balance?: number | null;
  currency?: string;
  balanceText: string;
  message?: string;
};

export type ProviderBalanceResponse = {
  updatedAt: number;
  cached: boolean;
  cacheTtl: number;
  providers: ProviderBalance[];
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

export async function fetchProviderBalances(refresh = false, timeoutMs = 15_000): Promise<ProviderBalanceResponse> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(`/api/provider/balances${refresh ? '?refresh=1' : ''}`, {
    method: 'GET',
    credentials: 'same-origin',
    signal: controller.signal
  }).finally(() => window.clearTimeout(timer));
  const data = await readJsonSafely(response);
  if (!response.ok) {
    throw new Error(data?.message || `请求失败：${response.status}`);
  }
  return {
    updatedAt: Number(data?.updatedAt || 0),
    cached: Boolean(data?.cached),
    cacheTtl: Number(data?.cacheTtl || 60),
    providers: Array.isArray(data?.providers) ? (data.providers as ProviderBalance[]) : []
  };
}
