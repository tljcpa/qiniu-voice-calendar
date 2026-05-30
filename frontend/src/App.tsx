import { useEffect, useRef, useState, type ReactNode } from "react";
import CalendarView from "./components/CalendarView";
import ConversationPanel from "./components/ConversationPanel";
import {
  confirmCommand,
  confirmPlan,
  deleteEvent,
  fetchEvents,
  resolveCommand,
  sendCommand,
} from "./api/client";
import EventDetail from "./components/EventDetail";
import AuthScreen from "./components/AuthScreen";
import { classifyConflictReply } from "./lib/intent";
import { useAuth } from "./hooks/useAuth";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "./hooks/useSpeechSynthesis";
import { useReminders } from "./hooks/useReminders";
import type { CalendarEvent, ChatMessage, CommandResponse } from "./types";

// 待续状态：上一轮系统反问后，记住上下文，下一句据此续接而非当新指令。
// - clarify：歧义澄清的候选（删/改"要哪一个"）→ 下一句走 resolve 指代消解
// - conflict：add 冲突的待建事件 → 下一句"好/就这个"走 confirm
type Pending =
  | {
      kind: "clarify";
      intent: string;
      candidates: CalendarEvent[];
      newValues: Record<string, unknown> | null;
    }
  | { kind: "conflict"; data: Record<string, unknown> }
  | { kind: "plan"; plan: Record<string, unknown>[] };


const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "你好，我是你的语音日历助手。点下方按钮，对我说“明天下午三点开产品评审会”试试，也可以直接打字。",
};

let msgSeq = 1;
function nextId() {
  msgSeq += 1;
  return `m${msgSeq}`;
}

export default function App() {
  const auth = useAuth();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  // 小屏单栏切换，默认对话（主交互）
  const [mobileTab, setMobileTab] = useState<"chat" | "calendar">("chat");
  const speech = useSpeechRecognition();
  const tts = useSpeechSynthesis();
  const reminders = useReminders();
  // 识别中的临时气泡 id
  const interimIdRef = useRef<string | null>(null);

  async function refreshEvents() {
    try {
      const data = await fetchEvents();
      setEvents(data);
    } catch (err) {
      console.error("拉取事件失败", err);
    }
  }

  // 登录后（及刷新带 token 时）加载事件；登出清空
  useEffect(() => {
    if (auth.token) {
      refreshEvents();
    } else {
      setEvents([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.token]);

  function appendMessage(msg: ChatMessage) {
    setMessages((prev) => [...prev, msg]);
  }

  // 根据响应更新"待续"状态
  function updatePending(resp: CommandResponse) {
    const isPickable = resp.intent === "delete" || resp.intent === "update";
    if (resp.needs_clarification && resp.candidates.length > 0 && isPickable) {
      setPending({
        kind: "clarify",
        intent: resp.intent,
        candidates: resp.candidates,
        newValues: resp.pending_new_values ?? null,
      });
    } else if (
      // 纯指代澄清：intent=clarify 但后端已列候选并给出最终动作 → 也建 pending
      resp.intent === "clarify" &&
      resp.needs_clarification &&
      resp.candidates.length > 0 &&
      resp.resolve_intent
    ) {
      setPending({
        kind: "clarify",
        intent: resp.resolve_intent,
        candidates: resp.candidates,
        newValues: resp.pending_new_values ?? null,
      });
    } else if (
      resp.intent === "add" &&
      resp.needs_clarification &&
      resp.pending_conflict
    ) {
      setPending({ kind: "conflict", data: resp.pending_conflict });
    } else if (
      resp.intent === "plan" &&
      resp.needs_clarification &&
      resp.pending_plan &&
      resp.pending_plan.length > 0
    ) {
      setPending({ kind: "plan", plan: resp.pending_plan });
    } else {
      setPending(null);
    }
  }

  // 在"待续"上下文里续接本句；返回 null 表示应作为全新指令处理
  async function continuePending(text: string): Promise<CommandResponse | null> {
    if (!pending) {
      return null;
    }
    if (pending.kind === "clarify") {
      return resolveCommand(
        text,
        pending.intent,
        pending.candidates,
        pending.newValues
      );
    }
    if (pending.kind === "plan") {
      // 规划待确认：肯定/"确认/添加"→创建全部；否则当新指令
      const ok =
        classifyConflictReply(text) === "accept" ||
        text.includes("确认") ||
        text.includes("添加") ||
        text.includes("都加");
      return ok ? confirmPlan(pending.plan) : null;
    }
    // conflict：分类回复——接受建议 / 坚持原时间 / 其它(当新指令)
    const reply = classifyConflictReply(text);
    if (reply === "insist") {
      return confirmCommand(pending.data, false);
    }
    if (reply === "accept") {
      return confirmCommand(pending.data, true);
    }
    return null;
  }

  // 处理一条最终指令文本（语音或打字）
  async function processCommand(text: string) {
    appendMessage({ id: nextId(), role: "user", text });
    setBusy(true);
    try {
      let resp = await continuePending(text);
      if (resp === null) {
        // 无待续上下文或冲突回复非接受/坚持 → 当作全新指令
        resp = await sendCommand(text);
      }
      appendMessage({
        id: nextId(),
        role: "assistant",
        text: resp.speech,
        events: resp.events,
      });
      tts.speak(resp.speech); // 语音闭环：朗读回应（亮点2）
      updatePending(resp);
      await refreshEvents();
    } catch (err) {
      setPending(null);
      appendMessage({
        id: nextId(),
        role: "assistant",
        text: `出错了：${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setBusy(false);
    }
  }

  // 录音按钮：开始/停止语音识别
  function handleMic() {
    if (speech.listening) {
      speech.stop();
      return;
    }
    interimIdRef.current = null;
    speech.start({
      onInterim: (interim) => {
        // 维护一条临时气泡，实时更新识别文本
        setMessages((prev) => {
          const id = interimIdRef.current;
          if (id) {
            return prev.map((m) =>
              m.id === id ? { ...m, text: interim } : m
            );
          }
          const newId = nextId();
          interimIdRef.current = newId;
          return [
            ...prev,
            { id: newId, role: "user", text: interim, interim: true },
          ];
        });
      },
      onFinal: (finalText) => {
        // 移除临时气泡，按正式指令处理
        const tempId = interimIdRef.current;
        interimIdRef.current = null;
        if (tempId) {
          setMessages((prev) => prev.filter((m) => m.id !== tempId));
        }
        if (finalText && finalText.trim()) {
          processCommand(finalText.trim());
        }
      },
      onError: (msg) => {
        const tempId = interimIdRef.current;
        interimIdRef.current = null;
        if (tempId) {
          setMessages((prev) => prev.filter((m) => m.id !== tempId));
        }
        appendMessage({ id: nextId(), role: "assistant", text: msg });
      },
    });
  }

  // 图形化删除（点日历事件 → 详情 → 删除），与语音删除互补
  async function handleDeleteEvent(event: CalendarEvent) {
    setSelectedEvent(null);
    try {
      await deleteEvent(event.id);
      appendMessage({
        id: nextId(),
        role: "assistant",
        text: `已删除${event.title}`,
      });
      await refreshEvents();
    } catch (err) {
      appendMessage({
        id: nextId(),
        role: "assistant",
        text: `删除失败：${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }

  let hint = "点击说话，或在下方打字";
  if (!speech.supported) {
    hint = "当前环境不支持麦克风，请用下方文字输入";
  }

  // 未登录 → 登录/注册页（所有 hook 已在上方按固定顺序调用，此处再分支渲染）
  if (!auth.user) {
    return <AuthScreen onLogin={auth.login} onRegister={auth.register} />;
  }

  return (
    <div className="flex h-full flex-col bg-canvas">
      <Header
        ttsEnabled={tts.enabled}
        speaking={tts.speaking}
        onToggleTts={tts.toggleEnabled}
        remindersOn={reminders.permission === "granted"}
        onEnableReminders={reminders.enable}
        engine={speech.engine}
        username={auth.user.username}
        onLogout={auth.logout}
      />
      {/* 小屏：对话/日历 标签切换（大屏并排，无此栏） */}
      <div className="flex border-b border-line lg:hidden">
        <TabButton
          active={mobileTab === "chat"}
          onClick={() => setMobileTab("chat")}
        >
          对话
        </TabButton>
        <TabButton
          active={mobileTab === "calendar"}
          onClick={() => setMobileTab("calendar")}
        >
          日历
        </TabButton>
      </div>
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-5">
        <section
          className={[
            "min-h-0 lg:col-span-3 lg:block",
            mobileTab === "chat" ? "block" : "hidden",
          ].join(" ")}
        >
          <ConversationPanel
            messages={messages}
            listening={speech.listening}
            hint={hint}
            busy={busy}
            onMic={handleMic}
            onSend={processCommand}
          />
        </section>
        <section
          className={[
            "min-h-0 lg:col-span-2 lg:block",
            mobileTab === "calendar" ? "block" : "hidden",
          ].join(" ")}
        >
          <CalendarView events={events} onEventClick={setSelectedEvent} />
        </section>
      </main>
      {selectedEvent && (
        <EventDetail
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onDelete={handleDeleteEvent}
        />
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "font-title flex-1 border-b-2 px-4 py-2 text-sm transition-colors",
        active
          ? "border-accent text-accent"
          : "border-transparent text-fg-muted hover:text-fg",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

interface HeaderProps {
  ttsEnabled: boolean;
  speaking: boolean;
  onToggleTts: () => void;
  remindersOn: boolean;
  onEnableReminders: () => void;
  engine: "azure" | "web" | null;
  username: string;
  onLogout: () => void;
}

function Header({
  ttsEnabled,
  speaking,
  onToggleTts,
  remindersOn,
  onEnableReminders,
  engine,
  username,
  onLogout,
}: HeaderProps) {
  let engineLabel = "Azure 语音";
  if (engine === "web") {
    engineLabel = "浏览器语音(降级)";
  }
  return (
    <header className="flex items-center gap-4 border-b border-line bg-panel px-4 py-2">
      {/* 简洁字标（文楷手写气质，无图标方块；wly 后续可换正式 logo 图） */}
      <h1 className="font-title shrink-0 whitespace-nowrap text-lg font-semibold tracking-wide text-fg">
        语音<span className="text-accent">日历</span>
      </h1>
      {/* 引擎状态：功能性而非营销文案（窄屏隐藏文字保留点） */}
      <span className="flex shrink-0 items-center gap-1.5 font-mono text-[11px] text-fg-dim">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" />
        <span className="hidden sm:inline">{engineLabel}</span>
      </span>
      <div className="ml-auto flex items-center gap-2">
        <ToggleChip
          on={remindersOn}
          label={remindersOn ? "提醒 开" : "提醒"}
          ariaLabel="开启日程提醒"
          onClick={onEnableReminders}
          icon={<BellIcon />}
        />
        <ToggleChip
          on={ttsEnabled}
          label={ttsEnabled ? "语音回复 开" : "语音回复 关"}
          ariaLabel={ttsEnabled ? "关闭语音回复" : "开启语音回复"}
          onClick={onToggleTts}
          icon={<SpeakerIcon muted={!ttsEnabled} pulsing={speaking} />}
        />
        {/* 当前用户 + 登出 */}
        <span className="hidden font-mono text-[11px] text-fg-dim sm:inline">
          {username}
        </span>
        <button
          type="button"
          onClick={onLogout}
          className="rounded border border-line bg-panel2 px-2.5 py-1 text-xs text-fg-muted hover:text-fg"
        >
          登出
        </button>
      </div>
    </header>
  );
}

interface ChipProps {
  on: boolean;
  label: string;
  ariaLabel: string;
  onClick: () => void;
  icon: ReactNode;
}

function ToggleChip({ on, label, ariaLabel, onClick, icon }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      className={[
        "flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors",
        on
          ? "border-accent-line bg-accent-soft text-accent"
          : "border-line bg-panel2 text-fg-muted hover:text-fg",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

function BellIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
      <path
        d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M10 19a2 2 0 0 0 4 0"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SpeakerIcon({ muted, pulsing }: { muted: boolean; pulsing: boolean }) {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      className={pulsing ? "animate-blink" : ""}
    >
      <path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor" />
      {!muted && (
        <path
          d="M16 8a5 5 0 0 1 0 8"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
