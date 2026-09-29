import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Alert, Box, Chip, Container, IconButton, LinearProgress, Stack, Typography } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage } from "../api/client";
import { getSuccessCriteria } from "../api/wcag";
import AppHeader from "../components/AppHeader";

const PRINCIPLE_COLORS = {
  Perceivable: "primary",
  Operable: "secondary",
  Understandable: "success",
  Robust: "warning",
};

const columns = [
  { field: "s_no", headerName: "S.No", width: 70 },
  { field: "sc_number", headerName: "SC Number", width: 110 },
  { field: "name", headerName: "Success Criterion Name", flex: 1, minWidth: 220 },
  { field: "wcag_version", headerName: "WCAG Version", width: 120 },
  { field: "level", headerName: "Level", width: 80 },
  {
    field: "principle",
    headerName: "Principle",
    width: 150,
    renderCell: (params) => <Chip size="small" label={params.value} color={PRINCIPLE_COLORS[params.value] || "default"} />,
  },
  { field: "guideline", headerName: "Guideline", width: 220 },
  { field: "description", headerName: "Description / Requirement", flex: 1.6, minWidth: 320 },
];

export default function SuccessCriteriaLibraryPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getSuccessCriteria()
      .then(setRows)
      .catch((err) => setError(extractErrorMessage(err, "Unable to load the Success Criteria Library.")))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppHeader />
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <IconButton onClick={() => navigate(-1)} size="small">
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h5" component="h1" fontWeight={600}>
            WCAG Success Criteria Library
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          All {rows.length || 56} WCAG 2.2 Level A and AA success criteria, grouped by the four WCAG
          principles (Perceivable, Operable, Understandable, Robust) - the master reference this platform's
          test cases are generated against.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <LinearProgress />
        ) : (
          <Box sx={{ height: 720, bgcolor: "background.paper" }}>
            <DataGrid
              rows={rows}
              columns={columns}
              getRowId={(row) => row.sc_number}
              disableRowSelectionOnClick
              getRowHeight={() => "auto"}
              initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
              pageSizeOptions={[25, 50, 100]}
              sx={{
                "& .MuiDataGrid-columnHeaders": {
                  bgcolor: "#1E3A5F",
                  color: "#fff",
                },
                "& .MuiDataGrid-columnHeaderTitle": {
                  fontWeight: 600,
                },
                "& .MuiDataGrid-sortIcon, & .MuiDataGrid-menuIconButton": {
                  color: "#fff",
                },
              }}
            />
          </Box>
        )}
      </Container>
    </Box>
  );
}
