import { useEffect, useRef, useState } from "react";
import CalendarView from "./components/CalendarView";
import ConversationPanel from "./components/ConversationPanel";
import { fetchEvents, sendCommand } from "./api/client";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";
import type { CalendarEvent, ChatMessage } from "./types";

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
  const speech = useSpeechRecognition();
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

  // 处理一条最终指令文本（语音或打字）
  async function processCommand(text: string) {
    appendMessage({ id: nextId(), role: "user", text });
    setBusy(true);
    try {
      const resp = await sendCommand(text);
      appendMessage({
        id: nextId(),
        role: "assistant",
        text: resp.speech,
        events: resp.events,
      });
      // 任何可能改变日程的意图后刷新日历
      await refreshEvents();
    } catch (err) {
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
      <Header />
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

function Header() {
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
      <span className="ml-auto rounded-full border border-neon-cyan/30 bg-neon-cyan/10 px-3 py-1 text-xs text-neon-cyan">
        语音交互为核心
      </span>
    </header>
  );
}
