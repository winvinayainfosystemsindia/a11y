import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Container,
  IconButton,
  LinearProgress,
  Paper,
  Popover,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getAuditExecution } from "../api/audit";
import { extractErrorMessage } from "../api/client";
import AppHeader from "../components/AppHeader";

const STAGE_ORDER = ["queued", "perceiving", "planning", "executing", "reflecting", "learning", "completed"];
const STAGE_LABELS = {
  queued: "Queued",
  perceiving: "Perceiving",
  planning: "Planning",
  executing: "Executing",
  reflecting: "Reflecting",
  learning: "Learning",
  completed: "Completed",
};
const EXECUTION_TERMINAL_STATUSES = new Set(["completed", "failed", "partial"]);
const POLL_INTERVAL_MS = 2000;

function stageChipColor(status) {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "queued") return "default";
  return "info";
}

function ErrorDetailButton({ message }) {
  const [anchorEl, setAnchorEl] = useState(null);
  return (
    <>
      <IconButton size="small" color="error" onClick={(event) => setAnchorEl(event.currentTarget)} aria-label="View error details">
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      >
        <Box sx={{ p: 2, maxWidth: 420 }}>
          <Typography variant="subtitle2" gutterBottom>
            Audit failed
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
            {message}
          </Typography>
        </Box>
      </Popover>
    </>
  );
}

function PageProgressRow({ page }) {
  if (!page.audit_run_id) {
    return (
      <TableRow hover>
        <TableCell>
          <Typography variant="body2" noWrap sx={{ maxWidth: 420 }}>
            {page.page_url || `Page #${page.page_id}`}
          </Typography>
        </TableCell>
        <TableCell>
          <Chip size="small" label="Not started" color="error" />
        </TableCell>
        <TableCell colSpan={2}>
          <Typography variant="body2" color="error">
            {page.message || "Could not start this audit."}
          </Typography>
        </TableCell>
      </TableRow>
    );
  }

  const isFailed = page.status === "failed";
  const isCompleted = page.status === "completed";
  const stageIndex = Math.max(0, STAGE_ORDER.indexOf(page.status));
  const progressPct = isCompleted
    ? 100
    : page.total_steps > 0
      ? Math.round((page.completed_steps / page.total_steps) * 100)
      : Math.round((stageIndex / (STAGE_ORDER.length - 1)) * 100);

  return (
    <TableRow hover>
      <TableCell>
        <Typography variant="body2" fontWeight={500} noWrap sx={{ maxWidth: 420 }}>
          {page.page_url || `Page #${page.page_id}`}
        </Typography>
      </TableCell>
      <TableCell>
        <Chip size="small" label={STAGE_LABELS[page.status] || page.status} color={stageChipColor(page.status)} />
      </TableCell>
      <TableCell sx={{ width: 220 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ flexGrow: 1 }}>
            <LinearProgress
              variant="determinate"
              value={progressPct}
              color={isFailed ? "error" : isCompleted ? "success" : "primary"}
              sx={{ height: 6, borderRadius: 3 }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 32, textAlign: "right" }}>
            {progressPct}%
          </Typography>
        </Stack>
        {page.status === "executing" && page.total_steps > 0 && (
          <Typography variant="caption" color="text.secondary">
            Step {Math.min(page.completed_steps + 1, page.total_steps)} of {page.total_steps}
          </Typography>
        )}
      </TableCell>
      <TableCell align="center" sx={{ width: 48 }}>
        {isFailed && <ErrorDetailButton message={page.error || "This audit run failed."} />}
      </TableCell>
    </TableRow>
  );
}

export default function AuditRunsPage() {
  const { projectId, executionId } = useParams();
  const navigate = useNavigate();

  const [execution, setExecution] = useState(null);
  const [pollError, setPollError] = useState("");
  const timerRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      const data = await getAuditExecution(executionId);
      setExecution(data);
      setPollError("");
      if (!EXECUTION_TERMINAL_STATUSES.has(data.status)) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    } catch (err) {
      setPollError(extractErrorMessage(err, "Unable to fetch audit progress."));
      timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    }
  }, [executionId]);

  useEffect(() => {
    poll();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [poll]);

  const isDone = execution && EXECUTION_TERMINAL_STATUSES.has(execution.status);
  const failedCount = execution?.pages.filter((p) => p.status === "failed").length ?? 0;
  const overallPct = execution && execution.total_pages > 0
    ? Math.round((execution.completed_pages / execution.total_pages) * 100)
    : 0;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 3 }}>
          <IconButton onClick={() => navigate(`/projects/${projectId}`)} size="small">
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h5" component="h1" fontWeight={600} sx={{ flexGrow: 1 }}>
            Audit progress
          </Typography>
        </Stack>

        {pollError && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {pollError}
          </Alert>
        )}

        {!execution ? (
          <LinearProgress />
        ) : execution.pages.length === 0 ? (
          <Alert severity="info">
            No pages were audited in this execution. Go back and select pages to audit.
          </Alert>
        ) : (
          <>
            <Card variant="outlined" sx={{ mb: 3, p: 2.5 }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={2} sx={{ mb: 1.5 }}>
                <Typography variant="subtitle1" fontWeight={600}>
                  {execution.completed_pages} of {execution.total_pages} pages complete
                </Typography>
                <Stack direction="row" spacing={1}>
                  {failedCount > 0 && <Chip size="small" label={`${failedCount} failed`} color="error" />}
                  <Chip
                    size="small"
                    label={isDone ? "Done" : "Running"}
                    color={isDone ? (failedCount > 0 ? "warning" : "success") : "info"}
                  />
                </Stack>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={overallPct}
                color={failedCount > 0 ? "warning" : "primary"}
                sx={{ height: 8, borderRadius: 4 }}
              />
            </Card>

            <Paper variant="outlined" sx={{ mb: 3, overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Page</TableCell>
                    <TableCell>Stage</TableCell>
                    <TableCell>Progress</TableCell>
                    <TableCell align="center" sx={{ width: 48 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {execution.pages.map((page) => (
                    <PageProgressRow key={page.page_id} page={page} />
                  ))}
                </TableBody>
              </Table>
            </Paper>

            {isDone && (
              <Button
                variant="contained"
                onClick={() => navigate(`/projects/${projectId}/audit-runs/${executionId}/results`)}
              >
                View combined report
              </Button>
            )}
          </>
        )}
      </Container>
    </Box>
  );
}
