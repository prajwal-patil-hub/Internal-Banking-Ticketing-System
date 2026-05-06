import axios, { AxiosError, AxiosInstance } from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const api: AxiosInstance = axios.create({
  baseURL,
  withCredentials: false,
  timeout: 15_000,
});

// Auth token interceptor (token store wired up in P1).
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

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
