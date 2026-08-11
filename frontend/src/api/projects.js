import { apiClient } from "./client";

export function listProjects() {
  return apiClient.get("/api/projects").then((res) => res.data);
}

export function createProject({ name, baseUrl }) {
  return apiClient.post("/api/projects", { name, base_url: baseUrl }).then((res) => res.data);
}

export function getProject(projectId) {
  return apiClient.get(`/api/projects/${projectId}`).then((res) => res.data);
}

export function startCrawl(projectId, options = {}) {
  return apiClient.post(`/api/projects/${projectId}/crawl`, options).then((res) => res.data);
}

export function getCrawlStatus(projectId) {
  return apiClient.get(`/api/projects/${projectId}/crawl/status`).then((res) => res.data);
}

export function listPages(projectId) {
  return apiClient.get(`/api/projects/${projectId}/pages`).then((res) => res.data);
}
