/**
 * Shared axios instance. The access token lives only in memory (set by
 * AuthContext, never localStorage). On a 401 we transparently try to
 * refresh the access token once using the refresh token, replay the
 * original request, and only give up (triggering logout) if that fails too.
 */
import axios from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

let currentAccessToken = null;
let refreshHandler = null; // async () => newAccessToken | throws
let onRefreshFailure = null; // () => void, called to force logout

export function setAccessToken(token) {
  currentAccessToken = token;
}

export function setRefreshHandler(fn) {
  refreshHandler = fn;
}

export function setOnRefreshFailure(fn) {
  onRefreshFailure = fn;
}

apiClient.interceptors.request.use((config) => {
  if (currentAccessToken && !config.skipAuth) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${currentAccessToken}`;
  }
  return config;
});

let refreshInFlight = null;

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const isAuthEndpoint =
      original?.url?.includes("/api/auth/login") ||
      original?.url?.includes("/api/auth/signup") ||
      original?.url?.includes("/api/auth/refresh");

    if (status === 401 && !original._retry && !isAuthEndpoint && refreshHandler) {
      original._retry = true;
      try {
        refreshInFlight = refreshInFlight || refreshHandler();
        const newToken = await refreshInFlight;
        refreshInFlight = null;
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      } catch (refreshError) {
        refreshInFlight = null;
        if (onRefreshFailure) onRefreshFailure();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export function extractErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  return error?.response?.data?.detail || fallback;
}
