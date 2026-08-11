import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  IconButton,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { startBatchAudit } from "../api/audit";
import { extractErrorMessage } from "../api/client";
import { getCrawlStatus, getProject, listPages, startCrawl } from "../api/projects";
import AppHeader from "../components/AppHeader";

const STATUS_COLORS = {
  idle: "default",
  running: "info",
  completed: "success",
  failed: "error",
};

const POLL_INTERVAL_MS = 2000;

const columns = [
  { field: "url", headerName: "URL", flex: 2, minWidth: 260 },
  { field: "page_title", headerName: "Page title", flex: 1.5, minWidth: 200 },
  { field: "status_code", headerName: "Status", width: 110 },
  {
    field: "discovered_at",
    headerName: "Discovered",
    width: 200,
    valueFormatter: (value) => (value ? new Date(value).toLocaleString() : ""),
  },
];

export default function ProjectPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [pages, setPages] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [selectedPageIds, setSelectedPageIds] = useState([]);
  const [auditStarting, setAuditStarting] = useState(false);
  const pollTimer = useRef(null);

  const loadProjectAndPages = useCallback(async () => {
    const [projectData, pagesData] = await Promise.all([getProject(projectId), listPages(projectId)]);
    setProject(projectData);
    setPages(pagesData);
    return projectData;
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    loadProjectAndPages()
      .catch((err) => setError(extractErrorMessage(err, "Unable to load this project.")))
      .finally(() => setLoading(false));

    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const pollStatus = useCallback(() => {
    pollTimer.current = setTimeout(async () => {
      try {
        const status = await getCrawlStatus(projectId);
        if (status.status === "running") {
          setCrawling(true);
          pollStatus();
        } else {
          setCrawling(false);
          const pagesData = await listPages(projectId);
          setPages(pagesData);
          setProject((prev) => (prev ? { ...prev, crawl_status: status.status } : prev));
        }
      } catch {
        setCrawling(false);
      }
    }, POLL_INTERVAL_MS);
  }, [projectId]);

  async function handleCrawl() {
    setError("");
    setCrawling(true);
    try {
      await startCrawl(projectId);
      pollStatus();
    } catch (err) {
      setCrawling(false);
      setError(extractErrorMessage(err, "Unable to start the crawl."));
    }
  }

  async function handleAuditSelected() {
    setError("");
    setAuditStarting(true);
    try {
      const response = await startBatchAudit(projectId, selectedPageIds);
      navigate(`/projects/${projectId}/audit-runs/${response.execution_id}`);
    } catch (err) {
      setError(extractErrorMessage(err, "Unable to start the audit."));
    } finally {
      setAuditStarting(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        <AppHeader />
        <LinearProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <IconButton onClick={() => navigate("/dashboard")} size="small">
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h5" component="h1" fontWeight={600}>
            {project?.name}
          </Typography>
          {project && (
            <Chip
              label={project.crawl_status}
              size="small"
              color={STATUS_COLORS[project.crawl_status] || "default"}
            />
          )}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          {project?.base_url}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}
        {project?.crawl_status === "failed" && project?.crawl_error && !error && (
          <Alert severity="warning" sx={{ mb: 3 }}>
            Last crawl failed: {project.crawl_error}
          </Alert>
        )}

        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 3 }} flexWrap="wrap">
          <Button
            variant="contained"
            startIcon={<TravelExploreIcon />}
            onClick={handleCrawl}
            disabled={crawling}
          >
            {crawling ? "Crawling..." : "Crawl Site"}
          </Button>
          <Button
            variant="outlined"
            startIcon={<FactCheckIcon />}
            onClick={handleAuditSelected}
            disabled={selectedPageIds.length === 0 || auditStarting}
          >
            {auditStarting
              ? "Starting audit..."
              : `Audit Selected Pages${selectedPageIds.length ? ` (${selectedPageIds.length})` : ""}`}
          </Button>
          {crawling && (
            <Typography variant="body2" color="text.secondary">
              Discovering pages... this list will update automatically.
            </Typography>
          )}
        </Stack>
        {crawling && <LinearProgress sx={{ mb: 3 }} />}

        <Typography variant="subtitle1" gutterBottom>
          Discovered pages ({pages.length})
        </Typography>
        <Box sx={{ height: 520, bgcolor: "background.paper" }}>
          <DataGrid
            rows={pages}
            columns={columns}
            getRowId={(row) => row.id}
            checkboxSelection
            disableRowSelectionOnClick
            rowSelectionModel={selectedPageIds}
            onRowSelectionModelChange={(model) => setSelectedPageIds(model)}
            initialState={{
              pagination: { paginationModel: { pageSize: 25 } },
            }}
            pageSizeOptions={[10, 25, 50, 100]}
          />
        </Box>
      </Container>
    </Box>
  );
}
