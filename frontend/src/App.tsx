import { useEffect, useRef, useState } from "react";
import CalendarView from "./components/CalendarView";
import ConversationPanel from "./components/ConversationPanel";
import { fetchEvents, resolveCommand, sendCommand } from "./api/client";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";
import { useSpeechSynthesis } from "./hooks/useSpeechSynthesis";
import { useReminders } from "./hooks/useReminders";
import type { CalendarEvent, ChatMessage, CommandResponse } from "./types";

// 待澄清状态：上一轮系统反问"要哪一个"时，记住意图与候选，
// 下一句用户指代（"第一个/下午那个"）走 resolve 而非新指令。
interface Pending {
  intent: string;
  candidates: CalendarEvent[];
  newValues: Record<string, unknown> | null;
}

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

  // 根据响应更新"待澄清"状态：delete/update 反问候选时记住，否则清空
  function updatePending(resp: CommandResponse) {
    const isPickable = resp.intent === "delete" || resp.intent === "update";
    if (resp.needs_clarification && resp.candidates.length > 0 && isPickable) {
      setPending({
        intent: resp.intent,
        candidates: resp.candidates,
        newValues: resp.pending_new_values ?? null,
      });
    } else {
      setPending(null);
    }
  }

  // 处理一条最终指令文本（语音或打字）
  async function processCommand(text: string) {
    appendMessage({ id: nextId(), role: "user", text });
    setBusy(true);
    try {
      let resp: CommandResponse;
      if (pending) {
        // 有待澄清：本句作为指代解析，选定上一轮候选
        resp = await resolveCommand(
          text,
          pending.intent,
          pending.candidates,
          pending.newValues
        );
      } else {
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

  let hint = "点击说话，或在下方打字";
  if (!speech.supported) {
    hint = "当前环境不支持麦克风，请用下方文字输入";
  }

  return (
    <div className="flex h-full flex-col">
      <Header
        ttsEnabled={tts.enabled}
        speaking={tts.speaking}
        onToggleTts={tts.toggleEnabled}
        remindersOn={reminders.permission === "granted"}
        onEnableReminders={reminders.enable}
      />
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-5">
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
          <CalendarView events={events} />
        </section>
      </main>
    </div>
  );
}

interface HeaderProps {
  ttsEnabled: boolean;
  speaking: boolean;
  onToggleTts: () => void;
  remindersOn: boolean;
  onEnableReminders: () => void;
}

function Header({
  ttsEnabled,
  speaking,
  onToggleTts,
  remindersOn,
  onEnableReminders,
}: HeaderProps) {
  return (
    <header className="flex items-center gap-3 border-b border-white/10 px-5 py-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-neon-cyan to-neon-violet shadow-glow">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <rect x="9" y="3" width="6" height="11" rx="3" fill="#0a0e1a" />
          <path
            d="M5 11a7 7 0 0 0 14 0"
            stroke="#0a0e1a"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <div>
        <h1 className="text-base font-bold tracking-wide text-white">
          语音日历
        </h1>
        <p className="text-[11px] text-slate-400">
          Azure 工业级中文语音 · 自然语言时间解析 · 对话式日程管理
        </p>
      </div>
      <div className="ml-auto flex items-center gap-3">
        {/* 提醒开关：申请浏览器通知权限 */}
        <button
          type="button"
          onClick={onEnableReminders}
          aria-label="开启日程提醒"
          className={[
            "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
            remindersOn
              ? "border-neon-cyan/40 bg-neon-cyan/10 text-neon-cyan"
              : "border-white/10 bg-ink-700/60 text-slate-400 hover:text-slate-200",
          ].join(" ")}
        >
          <span aria-hidden="true">🔔</span>
          {remindersOn ? "提醒 开" : "开启提醒"}
        </button>
        {/* 语音回复开关：体现"语音闭环"卖点 */}
        <button
          type="button"
          onClick={onToggleTts}
          aria-label={ttsEnabled ? "关闭语音回复" : "开启语音回复"}
          className={[
            "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
            ttsEnabled
              ? "border-neon-cyan/40 bg-neon-cyan/10 text-neon-cyan"
              : "border-white/10 bg-ink-700/60 text-slate-400",
          ].join(" ")}
        >
          <SpeakerIcon on={ttsEnabled} pulsing={speaking} />
          {ttsEnabled ? "语音回复 开" : "语音回复 关"}
        </button>
        <span className="rounded-full border border-neon-violet/30 bg-neon-violet/10 px-3 py-1 text-xs text-neon-violet">
          语音交互为核心
        </span>
      </div>
    </header>
  );
}

function SpeakerIcon({ on, pulsing }: { on: boolean; pulsing: boolean }) {
  const color = on ? "#22d3ee" : "#64748b";
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      className={pulsing ? "animate-pulse" : ""}
    >
      <path
        d="M4 9v6h4l5 4V5L8 9H4z"
        fill={color}
      />
      {on && (
        <path
          d="M16 8a5 5 0 0 1 0 8"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
