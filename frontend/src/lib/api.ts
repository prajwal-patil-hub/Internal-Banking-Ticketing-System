import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const api: AxiosInstance = axios.create({
  baseURL,
  withCredentials: false,
  timeout: 15_000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- Single-flight refresh on 401 -----------------------------------------
let refreshing: Promise<string | null> | null = null;

async function attemptRefresh(): Promise<string | null> {
  const raw = localStorage.getItem('success-auth');
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    const refreshToken: string | undefined = parsed?.state?.refreshToken;
    if (!refreshToken) return null;

    const resp = await axios.post(`${baseURL}/auth/refresh`, { refresh_token: refreshToken });
    const tokens = resp.data?.data;
    if (!tokens) return null;

    parsed.state.accessToken = tokens.access_token;
    parsed.state.refreshToken = tokens.refresh_token;
    localStorage.setItem('success-auth', JSON.stringify(parsed));
    localStorage.setItem('access_token', tokens.access_token);
    return tokens.access_token as string;
  } catch {
    localStorage.removeItem('access_token');
    localStorage.removeItem('success-auth');
    return null;
  }
}

api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError) => {
    const original = err.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined;
    const status = err.response?.status;
    const isAuthRoute = original?.url?.startsWith('/auth/');

    if (status === 401 && original && !original._retried && !isAuthRoute) {
      original._retried = true;
      refreshing ??= attemptRefresh().finally(() => { refreshing = null; });
      const newAccess = await refreshing;
      if (newAccess) {
        original.headers = { ...(original.headers ?? {}), Authorization: `Bearer ${newAccess}` };
        return api.request(original);
      }
      // Hard logout — let the route guard redirect to /login.
      window.dispatchEvent(new CustomEvent('auth:logout'));
    }
    return Promise.reject(err);
  },
);

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export function extractError(err: unknown): ApiError {
  if (err instanceof AxiosError && err.response?.data?.error) {
    return err.response.data.error as ApiError;
  }
  return { code: 'NETWORK_ERROR', message: 'Network error.' };
}
