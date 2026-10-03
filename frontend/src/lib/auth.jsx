import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router";
import * as api from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = signed out

  const refresh = useCallback(() => api.me().then(setUser).catch(() => setUser(null)), []);
  useEffect(() => { refresh(); }, [refresh]);

  const value = {
    user,
    setUser,
    refresh,
    login: async (body) => setUser(await api.login(body)),
    signup: async (body) => setUser(await api.signup(body)),
    logout: async () => { await api.logout().catch(() => {}); setUser(null); },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function RequireAuth({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <p className="muted pad">Loading…</p>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return children;
}
