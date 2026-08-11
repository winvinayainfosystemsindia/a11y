import { apiClient } from "./client";

export function startAudit(projectId, pageId, conformanceLevel = "AA") {
  return apiClient
    .post(`/api/projects/${projectId}/pages/${pageId}/audit`, null, {
      params: { conformance_level: conformanceLevel },
    })
    .then((res) => res.data);
}

/**
 * Start a single execution covering every selected page - one execution_id,
 * one combined report, not N separate audits.
 */
export function startBatchAudit(projectId, pageIds, conformanceLevel = "AA") {
  return apiClient
    .post(`/api/projects/${projectId}/audit-batch`, {
      page_ids: pageIds,
      conformance_level: conformanceLevel,
    })
    .then((res) => res.data);
}

export function getAuditRun(auditRunId) {
  return apiClient.get(`/api/audit-runs/${auditRunId}`).then((res) => res.data);
}

export function getAuditRunResults(auditRunId) {
  return apiClient.get(`/api/audit-runs/${auditRunId}/results`).then((res) => res.data);
}

/**
 * Aggregate progress for a whole execution - one poll target covering every
 * page's status/stepper instead of one poll per page.
 */
export function getAuditExecution(executionId) {
  return apiClient.get(`/api/audit-executions/${executionId}`).then((res) => res.data);
}

/**
 * The single combined report (test cases + defects across every page) for
 * an execution.
 */
export function getAuditExecutionResults(executionId) {
  return apiClient.get(`/api/audit-executions/${executionId}/results`).then((res) => res.data);
}

/**
 * Manual QA override: patch a test case's pass/fail/needs_review verdict
 * and/or a defect's lifecycle status (Open/Fixed/Retest/...).
 */
export function overridePlanStep(auditRunId, planStepId, { status, defectStatus } = {}) {
  return apiClient
    .patch(`/api/audit-runs/${auditRunId}/plan-steps/${planStepId}`, {
      status: status ?? null,
      defect_status: defectStatus ?? null,
    })
    .then((res) => res.data);
}

/**
 * Download the combined Excel report (Defects + Test Cases) for an audit run.
 * Triggers a browser file-save dialog.
 */
export async function downloadAuditExcel(auditRunId) {
  const response = await apiClient.get(`/api/audit-runs/${auditRunId}/export/excel`, {
    responseType: "blob",
  });
  _triggerDownload(response.data, `audit_${auditRunId}_report.xlsx`);
}

/**
 * Download the IAAP-style Word document (.docx) for an audit run.
 * Triggers a browser file-save dialog.
 */
export async function downloadAuditWord(auditRunId) {
  const response = await apiClient.get(`/api/audit-runs/${auditRunId}/export/word`, {
    responseType: "blob",
  });
  _triggerDownload(response.data, `audit_${auditRunId}_iaap_report.docx`);
}

/**
 * Download the combined Excel workbook (all pages in the execution) for
 * the whole execution. Triggers a browser file-save dialog.
 */
export async function downloadExecutionExcel(executionId) {
  const response = await apiClient.get(`/api/audit-executions/${executionId}/export/excel`, {
    responseType: "blob",
  });
  _triggerDownload(response.data, `audit_execution_${executionId}_report.xlsx`);
}

/**
 * Download the combined IAAP-style Word document (all pages in the
 * execution) for the whole execution. Triggers a browser file-save dialog.
 */
export async function downloadExecutionWord(executionId) {
  const response = await apiClient.get(`/api/audit-executions/${executionId}/export/word`, {
    responseType: "blob",
  });
  _triggerDownload(response.data, `audit_execution_${executionId}_iaap_report.docx`);
}

function _triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
