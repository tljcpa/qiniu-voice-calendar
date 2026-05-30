// 登录态管理：token+user 存 localStorage，跨设备/刷新保持登录。
import { useCallback, useEffect, useState } from "react";
import {
  login as apiLogin,
  register as apiRegister,
  setAuthToken,
  setOnUnauthorized,
} from "../api/client";

const TOKEN_KEY = "vc_token";
const USER_KEY = "vc_user";

export interface AuthUser {
  id: number;
  username: string;
}

function loadUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function useAuth() {
  // 初始化即把 token 同步给 client，避免首屏请求早于 effect 而 401
  const [token, setToken] = useState<string | null>(() => {
    const t = localStorage.getItem(TOKEN_KEY);
    setAuthToken(t);
    return t;
  });
  const [user, setUser] = useState<AuthUser | null>(loadUser);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setAuthToken(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }, []);

  // token 失效（曾登录却 401）→ 自动登出
  useEffect(() => {
    setOnUnauthorized(logout);
  }, [logout]);

  function persist(res: { token: string; user: AuthUser }) {
    setAuthToken(res.token);
    setToken(res.token);
    setUser(res.user);
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
  }

  async function login(username: string, password: string) {
    persist(await apiLogin(username, password));
  }
  async function register(username: string, password: string) {
    persist(await apiRegister(username, password));
  }

  return { token, user, login, register, logout };
}
