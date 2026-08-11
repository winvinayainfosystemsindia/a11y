import AddIcon from "@mui/icons-material/Add";
import LanguageIcon from "@mui/icons-material/Language";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createProject, listProjects } from "../api/projects";
import { extractErrorMessage } from "../api/client";
import AppHeader from "../components/AppHeader";

const STATUS_COLORS = {
  idle: "default",
  running: "info",
  completed: "success",
  failed: "error",
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function loadProjects() {
    setLoading(true);
    setLoadError("");
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err) {
      setLoadError(extractErrorMessage(err, "Unable to load your projects."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  function openDialog() {
    setName("");
    setBaseUrl("");
    setFieldErrors({});
    setFormError("");
    setDialogOpen(true);
  }

  function validate() {
    const errors = {};
    if (!name.trim()) errors.name = "Project name is required";
    if (!/^https?:\/\/.+/i.test(baseUrl.trim())) {
      errors.baseUrl = "Enter a valid URL starting with http:// or https://";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleCreate(e) {
    e.preventDefault();
    setFormError("");
    if (!validate()) return;

    setSubmitting(true);
    try {
      const project = await createProject({ name: name.trim(), baseUrl: baseUrl.trim() });
      setDialogOpen(false);
      setProjects((prev) => [project, ...prev]);
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setFormError(extractErrorMessage(err, "Unable to create the project."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
          <Typography variant="h5" component="h1" fontWeight={600}>
            Your projects
          </Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={openDialog}>
            New project
          </Button>
        </Stack>

        {loadError && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {loadError}
          </Alert>
        )}

        {!loading && projects.length === 0 && !loadError && (
          <Alert severity="info">
            No projects yet. Click &quot;New project&quot; to add the first site you want to audit.
          </Alert>
        )}

        <Grid container spacing={3}>
          {projects.map((project) => (
            <Grid item xs={12} sm={6} md={4} key={project.id}>
              <Card elevation={2}>
                <CardActionArea onClick={() => navigate(`/projects/${project.id}`)}>
                  <CardContent>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                      <LanguageIcon color="action" fontSize="small" />
                      <Typography variant="h6" component="div" noWrap>
                        {project.name}
                      </Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary" noWrap gutterBottom>
                      {project.base_url}
                    </Typography>
                    <Chip
                      label={project.crawl_status}
                      size="small"
                      color={STATUS_COLORS[project.crawl_status] || "default"}
                    />
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New project</DialogTitle>
        <Box component="form" onSubmit={handleCreate} noValidate>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {formError && <Alert severity="error">{formError}</Alert>}
              <TextField
                label="Project name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                error={Boolean(fieldErrors.name)}
                helperText={fieldErrors.name}
                fullWidth
                autoFocus
              />
              <TextField
                label="Base URL"
                placeholder="https://example.com"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                error={Boolean(fieldErrors.baseUrl)}
                helperText={fieldErrors.baseUrl}
                fullWidth
              />
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              {submitting ? "Creating..." : "Create project"}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
