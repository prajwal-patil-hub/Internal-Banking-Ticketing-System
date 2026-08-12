import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/**
 * Timeout for AI-backed calls.
 *
 * The 15s default is right for CRUD but far too short for a local LLM: a cold
 * GLM-4 request on Ollama has to load the weights before emitting a token and
 * routinely takes 30-90s. Anything AI-backed must opt into this longer budget,
 * otherwise axios aborts a request the backend is still happily serving.
 * Kept slightly above the backend's AI_TIMEOUT_SECONDS so the server's own
 * timeout (with its actionable error message) is what the user sees.
 */
export const AI_TIMEOUT_MS = 190_000;

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

/** Base URL for callers that can't go through axios (e.g. fetch-based SSE). */
export const API_BASE_URL = baseURL;

// --- Single-flight refresh on 401 -----------------------------------------
let refreshing: Promise<string | null> | null = null;

/**
 * Refresh the access token, coalescing concurrent callers into one request.
 *
 * Exported so the streaming client can reuse the exact same 401 handling as
 * the axios interceptor instead of reimplementing it and drifting.
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= attemptRefresh().finally(() => { refreshing = null; });
  return refreshing;
}

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
      const newAccess = await refreshAccessToken();
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
  if (err instanceof AxiosError) {
    if (err.response?.data?.error) {
      return err.response.data.error as ApiError;
    }
    if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
      return {
        code: 'TIMEOUT',
        message: 'The request timed out. The local AI model may still be loading — try again.',
      };
    }
    if (!err.response) {
      return {
        code: 'NETWORK_ERROR',
        message: 'Could not reach the API. Check that the backend is running.',
      };
    }
    return { code: `HTTP_${err.response.status}`, message: err.message };
  }
  return { code: 'NETWORK_ERROR', message: 'Network error.' };
}
