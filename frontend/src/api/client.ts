// 后端 API 客户端。所有网络调用收拢于此，组件不直接 fetch。
import type { CalendarEvent, CommandResponse, SpeechToken } from "../types";

// 同源部署时走相对路径；开发期由 vite proxy 转发到 8081。
const BASE = "";

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`API ${resp.status}: ${detail}`);
  }
  return (await resp.json()) as T;
}

/** 按时间范围拉取事件（FullCalendar 视图用）。 */
export async function fetchEvents(
  start?: string,
  end?: string
): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }
  const qs = params.toString();
  const url = qs ? `${BASE}/api/events?${qs}` : `${BASE}/api/events`;
  const resp = await fetch(url);
  return handle<CalendarEvent[]>(resp);
}

/** 发送一条语音指令文本，返回执行结果与回应文案。 */
export async function sendCommand(
  text: string,
  force = false
): Promise<CommandResponse> {
  const resp = await fetch(`${BASE}/api/voice/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, force }),
  });
  return handle<CommandResponse>(resp);
}

/** 取 Azure Speech 短时令牌（浏览器 SDK 用）。 */
export async function fetchSpeechToken(): Promise<SpeechToken> {
  const resp = await fetch(`${BASE}/api/speech/token`, { method: "POST" });
  return handle<SpeechToken>(resp);
}
