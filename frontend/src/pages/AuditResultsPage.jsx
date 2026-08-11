import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArticleIcon from "@mui/icons-material/Article";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Grid,
  IconButton,
  LinearProgress,
  Popover,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  Tooltip,
  Typography,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { downloadExecutionExcel, downloadExecutionWord, getAuditExecutionResults, overridePlanStep } from "../api/audit";
import { API_BASE_URL, extractErrorMessage } from "../api/client";
import AppHeader from "../components/AppHeader";

const STATUS_COLORS = { pass: "success", fail: "error", needs_review: "warning" };
const STATUS_OPTIONS = ["pass", "fail", "needs_review"];
const DEFECT_STATUS_OPTIONS = ["Open", "In Progress", "Fixed", "Retest", "Closed", "Won't Fix"];
const DEFECT_STATUS_COLORS = {
  Open: "error",
  "In Progress": "warning",
  Retest: "warning",
  Fixed: "success",
  Closed: "success",
  "Won't Fix": "default",
};
const SEVERITY_COLORS = {
  Critical: "error",
  High: "error",
  Medium: "warning",
  Low: "default",
  "N/A": "default",
  "Review Needed": "warning",
};
const VERIFICATION_STATUS_COLORS = {
  Confirmed: "default",
  "AI Judgment - Needs Review": "warning",
};

function confidenceColor(confidence) {
  if (confidence >= 0.8) return "success";
  if (confidence >= 0.6) return "warning";
  return "error";
}

function ReasonPopoverButton({ label, reasoning, confidence, isLowConfidence }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const open = Boolean(anchorEl);

  return (
    <>
      <IconButton size="small" onClick={(event) => setAnchorEl(event.currentTarget)} aria-label={label}>
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      >
        <Box sx={{ p: 2, maxWidth: 360 }}>
          <Typography variant="subtitle2" gutterBottom>
            {label}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {reasoning || "No reasoning recorded."}
          </Typography>
          {isLowConfidence && (
            <Alert severity="warning" sx={{ mt: 1.5 }}>
              Low confidence ({Math.round(confidence * 100)}%) - review manually.
            </Alert>
          )}
        </Box>
      </Popover>
    </>
  );
}

function ScreenshotLink({ path }) {
  if (!path) return null;
  return (
    <a href={`${API_BASE_URL}${path}`} target="_blank" rel="noreferrer">
      View
    </a>
  );
}

const testCaseColumns = [
  { field: "test_case_id", headerName: "TC ID", width: 110 },
  { field: "tc_name", headerName: "Test Case Name", flex: 1.2, minWidth: 220 },
  { field: "page_title", headerName: "Page", flex: 1, minWidth: 160 },
  { field: "page_url", headerName: "Page URL", flex: 1, minWidth: 200 },
  { field: "principle", headerName: "Principle", width: 130 },
  { field: "criteria", headerName: "Criteria", width: 220 },
  { field: "level", headerName: "Level", width: 70 },
  { field: "element_type", headerName: "Element / Component Type on Page", width: 220 },
  {
    field: "severity",
    headerName: "Severity",
    width: 130,
    renderCell: (params) => <Chip size="small" label={params.value} color={SEVERITY_COLORS[params.value] || "default"} />,
  },
  {
    field: "status",
    headerName: "Status",
    width: 150,
    editable: true,
    type: "singleSelect",
    valueOptions: STATUS_OPTIONS,
    renderCell: (params) => <Chip size="small" label={params.value} color={STATUS_COLORS[params.value] || "default"} />,
  },
  { field: "description", headerName: "Description", flex: 1.4, minWidth: 220 },
  { field: "expected_result", headerName: "Expected", flex: 1.2, minWidth: 200 },
  { field: "actual_result", headerName: "Actual", flex: 1.2, minWidth: 200 },
  { field: "steps_to_reproduce", headerName: "Steps to Reproduce", flex: 1.2, minWidth: 220 },
  { field: "remediation", headerName: "Remediation", flex: 1.2, minWidth: 220 },
  {
    field: "screenshot",
    headerName: "Screenshot",
    width: 110,
    renderCell: (params) => <ScreenshotLink path={params.value} />,
  },
  {
    field: "confidence",
    headerName: "Confidence",
    width: 130,
    renderCell: (params) => (
      <Chip size="small" label={`${Math.round(params.value * 100)}%`} color={confidenceColor(params.value)} />
    ),
  },
  {
    field: "why",
    headerName: "Why?",
    width: 70,
    sortable: false,
    filterable: false,
    renderCell: (params) => (
      <ReasonPopoverButton
        label="Why the AI flagged this"
        reasoning={params.row.reasoning}
        confidence={params.row.confidence}
        isLowConfidence={params.row.is_low_confidence}
      />
    ),
  },
];

const defectColumns = [
  { field: "defect_id", headerName: "Defect ID", width: 120 },
  { field: "test_case_id", headerName: "TC ID", width: 110 },
  { field: "page_title", headerName: "Page", flex: 1, minWidth: 160 },
  { field: "page_url", headerName: "Page URL", flex: 1, minWidth: 200 },
  { field: "principle", headerName: "Principle", width: 130 },
  { field: "criteria", headerName: "Criteria", width: 220 },
  { field: "level", headerName: "Level", width: 70 },
  { field: "element_type", headerName: "Element / Component Type on Page", width: 220 },
  {
    field: "severity",
    headerName: "Severity",
    width: 130,
    renderCell: (params) => <Chip size="small" label={params.value} color={SEVERITY_COLORS[params.value] || "default"} />,
  },
  {
    field: "status",
    headerName: "Status",
    width: 130,
    renderCell: (params) => <Chip size="small" label={params.value} color={STATUS_COLORS[params.value] || "default"} />,
  },
  {
    field: "verification_status",
    headerName: "Verification Status",
    width: 190,
    // "Confirmed" (a deterministic tool failure) vs "AI Judgment - Needs
    // Review" (an unconfirmed AI finding) - kept as its own column, distinct
    // from Severity, so this can't be summed/filtered as if every row were
    // an equally-verified defect.
    renderCell: (params) => (
      <Chip size="small" label={params.value} color={VERIFICATION_STATUS_COLORS[params.value] || "default"} />
    ),
  },
  {
    field: "confidence",
    headerName: "Confidence",
    width: 130,
    renderCell: (params) =>
      params.value == null ? "" : (
        <Chip size="small" label={`${Math.round(params.value * 100)}%`} color={confidenceColor(params.value)} />
      ),
  },
  {
    field: "defect_status",
    headerName: "Defect Status",
    width: 150,
    editable: true,
    type: "singleSelect",
    valueOptions: DEFECT_STATUS_OPTIONS,
    renderCell: (params) => (
      <Chip size="small" label={params.value} color={DEFECT_STATUS_COLORS[params.value] || "default"} />
    ),
  },
  { field: "description", headerName: "Description", flex: 1.3, minWidth: 220 },
  { field: "expected_result", headerName: "Expected", flex: 1, minWidth: 180 },
  { field: "actual_result", headerName: "Actual", flex: 1, minWidth: 180 },
  { field: "steps_to_reproduce", headerName: "Steps to Reproduce", flex: 1.1, minWidth: 200 },
  { field: "suggestion_to_fix", headerName: "Suggestion to Fix", flex: 1.3, minWidth: 220 },
  {
    field: "html_snippet",
    headerName: "HTML Snippet",
    flex: 1,
    minWidth: 220,
    renderCell: (params) =>
      params.value ? (
        <Typography
          variant="caption"
          component="code"
          sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", display: "block", py: 1 }}
        >
          {params.value}
        </Typography>
      ) : (
        ""
      ),
  },
  {
    field: "screenshot",
    headerName: "Screenshot",
    width: 110,
    renderCell: (params) => <ScreenshotLink path={params.value} />,
  },
];

function StatCard({ label, value }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h4" fontWeight={700}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
      </CardContent>
    </Card>
  );
}

function PageSummaryTable({ pages }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" gutterBottom>
        Pages in this report ({pages.length})
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Page</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Test Cases</TableCell>
            <TableCell align="right">Defects</TableCell>
            <TableCell align="right">Pass Rate</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {pages.map((page) => (
            <TableRow key={page.page_id}>
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {page.page_title || "(untitled page)"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {page.page_url}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={page.status}
                  color={page.status === "completed" ? "success" : page.status === "failed" ? "error" : "default"}
                />
              </TableCell>
              <TableCell align="right">{page.total_test_cases ?? "—"}</TableCell>
              <TableCell align="right">{page.total_defects ?? "—"}</TableCell>
              <TableCell align="right">{page.total_test_cases != null ? `${page.pass_rate}%` : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function BreakdownTable({ title, rows }) {
  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        {title}
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{title === "By Principle" ? "Principle" : "Level"}</TableCell>
            <TableCell align="right">Total</TableCell>
            <TableCell align="right">Passed</TableCell>
            <TableCell align="right">Failed</TableCell>
            <TableCell align="right">Review</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell>{row.label}</TableCell>
              <TableCell align="right">{row.total}</TableCell>
              <TableCell align="right">{row.passed}</TableCell>
              <TableCell align="right">{row.failed}</TableCell>
              <TableCell align="right">{row.needs_review}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

export default function AuditResultsPage() {
  const { projectId, executionId } = useParams();
  const navigate = useNavigate();

  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(0);
  const [downloadingExcel, setDownloadingExcel] = useState(false);
  const [downloadingWord, setDownloadingWord] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [overrideError, setOverrideError] = useState("");

  const handleDownloadExcel = async () => {
    setDownloadingExcel(true);
    setDownloadError("");
    try {
      await downloadExecutionExcel(executionId);
    } catch (err) {
      setDownloadError(extractErrorMessage(err, "Failed to download Excel report."));
    } finally {
      setDownloadingExcel(false);
    }
  };

  const handleDownloadWord = async () => {
    setDownloadingWord(true);
    setDownloadError("");
    try {
      await downloadExecutionWord(executionId);
    } catch (err) {
      setDownloadError(extractErrorMessage(err, "Failed to download Word report."));
    } finally {
      setDownloadingWord(false);
    }
  };

  // Rows in a combined report can each belong to a different page's
  // AuditRun, so the override target comes from the row itself, not a
  // single URL param the way the old single-page results page worked.
  const handleTestCaseStatusUpdate = async (newRow, oldRow) => {
    if (newRow.status === oldRow.status) return oldRow;
    try {
      await overridePlanStep(newRow.audit_run_id, newRow.plan_step_id, { status: newRow.status });
    } catch (err) {
      setOverrideError(extractErrorMessage(err, "Failed to update test case status."));
      throw err;
    }
    setResults((prev) => ({
      ...prev,
      test_cases: prev.test_cases.map((row) => (row.test_case_id === newRow.test_case_id ? newRow : row)),
    }));
    return newRow;
  };

  const handleDefectStatusUpdate = async (newRow, oldRow) => {
    if (newRow.defect_status === oldRow.defect_status) return oldRow;
    try {
      await overridePlanStep(newRow.audit_run_id, newRow.plan_step_id, { defectStatus: newRow.defect_status });
    } catch (err) {
      setOverrideError(extractErrorMessage(err, "Failed to update defect status."));
      throw err;
    }
    setResults((prev) => ({
      ...prev,
      defects: prev.defects.map((row) => (row.defect_id === newRow.defect_id ? newRow : row)),
    }));
    return newRow;
  };

  useEffect(() => {
    setLoading(true);
    getAuditExecutionResults(executionId)
      .then(setResults)
      .catch((err) => setError(extractErrorMessage(err, "Unable to load audit results.")))
      .finally(() => setLoading(false));
  }, [executionId]);

  if (loading) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        <AppHeader />
        <LinearProgress />
      </Box>
    );
  }

  const report = results?.report;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
          <IconButton onClick={() => navigate(`/projects/${projectId}/audit-runs/${executionId}`)} size="small">
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h5" component="h1" fontWeight={600} sx={{ flexGrow: 1 }}>
            Accessibility Audit Report
          </Typography>
          {results && (
            <Stack direction="row" spacing={1}>
              <Tooltip title="Download Defects + Test Cases as a single Excel workbook (2 sheets)">
                <span>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<FileDownloadIcon />}
                    onClick={handleDownloadExcel}
                    disabled={downloadingExcel}
                    sx={{
                      bgcolor: "#1E3A5F",
                      "&:hover": { bgcolor: "#2a4f82" },
                      textTransform: "none",
                      fontWeight: 600,
                    }}
                  >
                    {downloadingExcel ? "Downloading…" : "Download Excel Report"}
                  </Button>
                </span>
              </Tooltip>
              <Tooltip title="Download IAAP-style audit report as a Word document (.docx)">
                <span>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<ArticleIcon />}
                    onClick={handleDownloadWord}
                    disabled={downloadingWord}
                    sx={{
                      borderColor: "#1E3A5F",
                      color: "#1E3A5F",
                      "&:hover": { borderColor: "#2a4f82", bgcolor: "rgba(30,58,95,0.06)" },
                      textTransform: "none",
                      fontWeight: 600,
                    }}
                  >
                    {downloadingWord ? "Downloading…" : "Download IAAP Word Report"}
                  </Button>
                </span>
              </Tooltip>
            </Stack>
          )}
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {downloadError && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setDownloadError("")}>
            {downloadError}
          </Alert>
        )}

        {overrideError && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setOverrideError("")}>
            {overrideError}
          </Alert>
        )}

        {results && (
          <>
            <Typography variant="subtitle1" fontWeight={600}>
              Combined report &middot; {results.pages.length} page{results.pages.length === 1 ? "" : "s"}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              WCAG {results.conformance_level}
            </Typography>

            <PageSummaryTable pages={results.pages} />

            {report?.executive_summary && (
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Executive Summary
                </Typography>
                {report.executive_summary}
              </Alert>
            )}

            {results.low_confidence_test_case_ids?.length > 0 && (
              <Alert severity="warning" sx={{ mb: 3 }}>
                {results.low_confidence_test_case_ids.length} finding(s) flagged as low-confidence - review these
                manually: {results.low_confidence_test_case_ids.join(", ")}
              </Alert>
            )}

            {report && (
              <>
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid item xs={6} sm={3}>
                    <StatCard label="Test Cases" value={report.total_test_cases} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <StatCard label="Defects" value={report.total_defects} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <StatCard label="Pass Rate" value={`${report.pass_rate}%`} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <StatCard label="Conformance Level" value={results.conformance_level} />
                  </Grid>
                </Grid>

                <Grid container spacing={3} sx={{ mb: 1 }}>
                  <Grid item xs={12} md={6}>
                    <BreakdownTable title="By Principle" rows={report.by_principle} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <BreakdownTable title="By Level" rows={report.by_level} />
                  </Grid>
                </Grid>

                {Object.keys(report.by_severity || {}).length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" sx={{ mr: 1, alignSelf: "center" }}>
                      Defects by severity:
                    </Typography>
                    {Object.entries(report.by_severity).map(([severity, count]) => (
                      <Chip
                        key={severity}
                        size="small"
                        label={`${severity}: ${count}`}
                        color={SEVERITY_COLORS[severity] || "default"}
                      />
                    ))}
                  </Stack>
                )}

                <Accordion sx={{ mb: 3 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="body2">Methodology</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" color="text.secondary">
                      {report.methodology}
                    </Typography>
                  </AccordionDetails>
                </Accordion>
              </>
            )}

            <Tabs value={tab} onChange={(_e, value) => setTab(value)} sx={{ mb: 1 }}>
              <Tab label={`Test Cases (${results.test_cases.length})`} />
              <Tab label={`Defects (${results.defects.length})`} />
            </Tabs>

            <Box sx={{ height: 640, bgcolor: "background.paper", overflowX: "auto" }}>
              {tab === 0 ? (
                <DataGrid
                  rows={results.test_cases}
                  columns={testCaseColumns}
                  getRowId={(row) => row.test_case_id}
                  disableRowSelectionOnClick
                  getRowHeight={() => "auto"}
                  initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                  pageSizeOptions={[10, 25, 50, 100]}
                  processRowUpdate={handleTestCaseStatusUpdate}
                  onProcessRowUpdateError={() => {}}
                />
              ) : (
                <DataGrid
                  rows={results.defects}
                  columns={defectColumns}
                  getRowId={(row) => row.defect_id}
                  disableRowSelectionOnClick
                  getRowHeight={() => "auto"}
                  initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                  pageSizeOptions={[10, 25, 50, 100]}
                  processRowUpdate={handleDefectStatusUpdate}
                  onProcessRowUpdateError={() => {}}
                />
              )}
            </Box>
          </>
        )}
      </Container>
    </Box>
  );
}
