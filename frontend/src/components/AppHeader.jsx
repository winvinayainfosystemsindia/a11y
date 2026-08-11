import LogoutIcon from "@mui/icons-material/Logout";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import { AppBar, Box, Button, Toolbar, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <AppBar position="static" color="primary" enableColorOnDark>
      <Toolbar>
        <Typography
          variant="h6"
          component="div"
          onClick={() => navigate("/dashboard")}
          sx={{ flexGrow: 1, cursor: "pointer" }}
        >
          Accessibility Audit Platform
        </Typography>
        {user && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Button color="inherit" startIcon={<MenuBookIcon />} onClick={() => navigate("/wcag/success-criteria")}>
              Success Criteria Library
            </Button>
            <Typography variant="body2">{user.full_name}</Typography>
            <Button color="inherit" startIcon={<LogoutIcon />} onClick={handleLogout}>
              Logout
            </Button>
          </Box>
        )}
      </Toolbar>
    </AppBar>
  );
}
