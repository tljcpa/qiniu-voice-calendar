import { useEffect, useRef, useState, type ReactNode } from "react";
import CalendarView from "./components/CalendarView";
import ConversationPanel from "./components/ConversationPanel";
import {
  confirmCommand,
  deleteEvent,
  fetchEvents,
  resolveCommand,
  sendCommand,
} from "./api/client";
import EventDetail from "./components/EventDetail";
import { classifyConflictReply } from "./lib/intent";
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
  | { kind: "conflict"; data: Record<string, unknown> };


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
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
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

  useEffect(() => {
    refreshEvents();
  }, []);

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
      resp.intent === "add" &&
      resp.needs_clarification &&
      resp.pending_conflict
    ) {
      setPending({ kind: "conflict", data: resp.pending_conflict });
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

  return (
    <div className="flex h-full flex-col bg-canvas">
      <Header
        ttsEnabled={tts.enabled}
        speaking={tts.speaking}
        onToggleTts={tts.toggleEnabled}
        remindersOn={reminders.permission === "granted"}
        onEnableReminders={reminders.enable}
        engine={speech.engine}
      />
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-5">
        <section className="min-h-0 lg:col-span-3">
          <ConversationPanel
            messages={messages}
            listening={speech.listening}
            hint={hint}
            busy={busy}
            onMic={handleMic}
            onSend={processCommand}
          />
        </section>
        <section className="min-h-0 lg:col-span-2">
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

interface HeaderProps {
  ttsEnabled: boolean;
  speaking: boolean;
  onToggleTts: () => void;
  remindersOn: boolean;
  onEnableReminders: () => void;
  engine: "azure" | "web" | null;
}

function Header({
  ttsEnabled,
  speaking,
  onToggleTts,
  remindersOn,
  onEnableReminders,
  engine,
}: HeaderProps) {
  let engineLabel = "Azure 语音";
  if (engine === "web") {
    engineLabel = "浏览器语音(降级)";
  }
  return (
    <header className="flex items-center gap-4 border-b border-line bg-panel px-4 py-2">
      {/* 标识：极简字母组 + 名称，无渐变无图标光晕 */}
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-sm font-semibold text-accent">VC</span>
        <h1 className="text-sm font-semibold text-fg">语音日历</h1>
      </div>
      {/* 引擎状态：功能性而非营销文案 */}
      <span className="flex items-center gap-1.5 font-mono text-[11px] text-fg-dim">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" />
        {engineLabel}
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
