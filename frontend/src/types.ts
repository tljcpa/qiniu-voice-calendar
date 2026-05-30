// 前后端共享的数据契约（与 backend app/ 的返回结构对齐）。
// 这是"契约冻结"文件——后续前端各组件依赖此处类型，改动需前后端同步。

/** 日历事件（对应后端 Event.to_dict）。时间为 ISO8601 字符串。 */
export interface CalendarEvent {
  id: number;
  title: string;
  start_at: string;
  end_at: string | null;
  location: string | null;
  attendees: string[];
  note: string | null;
}

/** 语音指令返回（对应后端 voice_command.handle_command）。 */
export interface CommandResponse {
  intent: "add" | "delete" | "view" | "update" | "clarify" | "unknown";
  ok: boolean;
  /** 给 TTS 播报的中文回应文案 */
  speech: string;
  needs_clarification: boolean;
  clarification: string | null;
  /** 歧义时的候选事件 */
  candidates: CalendarEvent[];
  /** 受影响或查询到的事件 */
  events: CalendarEvent[];
  /** update 澄清时待应用的新值，多轮 resolve 时原样回传 */
  pending_new_values?: Record<string, unknown> | null;
  /** add 冲突时待建事件与建议时间，用户答"好/就这个"时回传 confirm */
  pending_conflict?: Record<string, unknown> | null;
  /** intent=clarify 但已列候选时，指代消解最终要执行的动作（delete/update） */
  resolve_intent?: "delete" | "update" | null;
  /** intent=plan 待确认的多事件计划，用户"好/确认"时回传创建 */
  pending_plan?: Record<string, unknown>[] | null;
  error?: string;
}

/** Azure Speech 短时令牌（对应后端 /api/speech/token）。 */
export interface SpeechToken {
  token: string;
  region: string;
}

/** 对话流中的一条消息（前端本地状态，非后端结构）。 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** 助手消息可携带受影响事件，用于在气泡里展示 */
  events?: CalendarEvent[];
  /** 是否为"识别中"的临时文本 */
  interim?: boolean;
}
