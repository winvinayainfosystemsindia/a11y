import { apiClient } from "./client";

export function getSuccessCriteria(level) {
  return apiClient
    .get("/api/wcag/success-criteria", { params: level ? { level } : {} })
    .then((res) => res.data.items);
}
