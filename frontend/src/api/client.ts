// 后端 API 客户端。所有网络调用收拢于此，组件不直接 fetch。
import type { CalendarEvent, CommandResponse, SpeechToken } from "../types";

// 同源部署时走相对路径；开发期由 vite proxy 转发到 8081。
const BASE = "";

// 登录态：token 注入 Authorization；401（且曾登录）触发登出回调。
let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}
export function setOnUnauthorized(cb: () => void): void {
  onUnauthorized = cb;
}

async function req<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) || {}),
  };
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  const resp = await fetch(`${BASE}${url}`, { ...init, headers });
  // 曾登录却收到 401 → token 失效，触发登出（登录请求本身无 token，不触发）
  if (resp.status === 401 && authToken && onUnauthorized) {
    onUnauthorized();
  }
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`API ${resp.status}: ${detail}`);
  }
  const text = await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export interface AuthResult {
  token: string;
  user: { id: number; username: string };
}

/** 注册新账户。 */
export function register(username: string, password: string): Promise<AuthResult> {
  return req<AuthResult>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** 登录。 */
export function login(username: string, password: string): Promise<AuthResult> {
  return req<AuthResult>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** 按时间范围拉取事件（FullCalendar 视图用）。 */
export function fetchEvents(start?: string, end?: string): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }
  const qs = params.toString();
  return req<CalendarEvent[]>(qs ? `/api/events?${qs}` : "/api/events");
}

/** 发送一条语音指令文本，返回执行结果与回应文案。 */
export function sendCommand(text: string, force = false): Promise<CommandResponse> {
  return req<CommandResponse>("/api/voice/command", {
    method: "POST",
    body: JSON.stringify({ text, force }),
  });
}

/** 多轮澄清第二步：带上一轮意图与候选，由用户指代选定并执行。 */
export function resolveCommand(
  text: string,
  intent: string,
  candidates: CalendarEvent[],
  newValues: Record<string, unknown> | null | undefined
): Promise<CommandResponse> {
  return req<CommandResponse>("/api/voice/resolve", {
    method: "POST",
    body: JSON.stringify({ text, intent, candidates, new_values: newValues ?? null }),
  });
}

/** 删除事件（图形化管理用）。 */
export function deleteEvent(id: number): Promise<void> {
  return req<void>(`/api/events/${id}`, { method: "DELETE" });
}

/** 冲突确认：接受建议时间 or 坚持原时间强建。 */
export function confirmCommand(
  data: Record<string, unknown>,
  acceptSuggestion: boolean
): Promise<CommandResponse> {
  return req<CommandResponse>("/api/voice/confirm", {
    method: "POST",
    body: JSON.stringify({ data, accept_suggestion: acceptSuggestion }),
  });
}

/** 确认多轮规划：一次性创建计划里的全部事件。 */
export function confirmPlan(
  plan: Record<string, unknown>[]
): Promise<CommandResponse> {
  return req<CommandResponse>("/api/voice/plan/confirm", {
    method: "POST",
    body: JSON.stringify({ plan }),
  });
}

/** 取 Azure Speech 短时令牌（浏览器 SDK 用）。 */
export function fetchSpeechToken(): Promise<SpeechToken> {
  return req<SpeechToken>("/api/speech/token", { method: "POST" });
}
