/**
 * Auth state for the whole app. The access token is kept ONLY in React
 * state (never localStorage) so it disappears the moment the tab closes
 * or reloads. The refresh token is kept in localStorage so a page reload
 * can silently re-establish a session without forcing a fresh login.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as authApi from "../api/auth";
import { setAccessToken as setClientAccessToken, setOnRefreshFailure, setRefreshHandler } from "../api/client";

const REFRESH_TOKEN_STORAGE_KEY = "a11y_refresh_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [accessToken, setAccessTokenState] = useState(null);
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const applyTokens = useCallback((tokenResponse) => {
    setAccessTokenState(tokenResponse.access_token);
    setClientAccessToken(tokenResponse.access_token);
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, tokenResponse.refresh_token);
  }, []);

  const clearSession = useCallback(() => {
    setAccessTokenState(null);
    setClientAccessToken(null);
    setUser(null);
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
  }, []);

  const doRefresh = useCallback(async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (!storedRefreshToken) {
      throw new Error("No refresh token available");
    }
    const tokenResponse = await authApi.refresh(storedRefreshToken);
    applyTokens(tokenResponse);
    return tokenResponse.access_token;
  }, [applyTokens]);

  useEffect(() => {
    setRefreshHandler(doRefresh);
    setOnRefreshFailure(clearSession);
  }, [doRefresh, clearSession]);

  // On first load, try to silently turn a stored refresh token into a
  // fresh access token + user profile, so the user doesn't have to log
  // in again after a page reload.
  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
      if (!storedRefreshToken) {
        setInitializing(false);
        return;
      }
      try {
        await doRefresh();
        const profile = await authApi.getMe();
        if (!cancelled) setUser(profile);
      } catch {
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email, password) => {
    const tokenResponse = await authApi.login({ email, password });
    applyTokens(tokenResponse);
    const profile = await authApi.getMe();
    setUser(profile);
    return profile;
  }, [applyTokens]);

  const signup = useCallback(async (fullName, email, password) => {
    await authApi.signup({ fullName, email, password });
  }, []);

  const logout = useCallback(async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    try {
      if (storedRefreshToken) await authApi.logout(storedRefreshToken);
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo(
    () => ({
      accessToken,
      user,
      initializing,
      isAuthenticated: Boolean(accessToken),
      login,
      signup,
      logout,
    }),
    [accessToken, user, initializing, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
