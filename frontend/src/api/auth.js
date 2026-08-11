import { apiClient } from "./client";

export function signup({ fullName, email, password }) {
  return apiClient
    .post("/api/auth/signup", { full_name: fullName, email, password })
    .then((res) => res.data);
}

export function login({ email, password }) {
  return apiClient.post("/api/auth/login", { email, password }).then((res) => res.data);
}

export function refresh(refreshToken) {
  return apiClient
    .post("/api/auth/refresh", { refresh_token: refreshToken }, { skipAuth: true })
    .then((res) => res.data);
}

export function logout(refreshToken) {
  return apiClient.post("/api/auth/logout", { refresh_token: refreshToken }).then((res) => res.data);
}

export function getMe() {
  return apiClient.get("/api/users/me").then((res) => res.data);
}
