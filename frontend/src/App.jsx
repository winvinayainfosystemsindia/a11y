import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import AuditResultsPage from "./pages/AuditResultsPage";
import AuditRunsPage from "./pages/AuditRunsPage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import ProjectPage from "./pages/ProjectPage";
import SignupPage from "./pages/SignupPage";
import SuccessCriteriaLibraryPage from "./pages/SuccessCriteriaLibraryPage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/wcag/success-criteria" element={<SuccessCriteriaLibraryPage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route path="/projects/:projectId/audit-runs/:executionId" element={<AuditRunsPage />} />
          <Route path="/projects/:projectId/audit-runs/:executionId/results" element={<AuditResultsPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}
