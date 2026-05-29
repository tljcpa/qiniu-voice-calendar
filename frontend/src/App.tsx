import { useEffect, useState } from "react";
import CalendarView from "./components/CalendarView";
import ConversationPanel from "./components/ConversationPanel";
import { fetchEvents } from "./api/client";
import type { CalendarEvent, ChatMessage } from "./types";

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "你好，我是你的语音日历助手。点下方按钮，对我说“明天下午三点开产品评审会”试试。",
};

export default function App() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [messages] = useState<ChatMessage[]>([WELCOME]);
  // PR10 录音按钮为视觉骨架，PR11 接入 Azure Speech
  const [listening] = useState(false);

  async function refreshEvents() {
    try {
      const data = await fetchEvents();
      setEvents(data);
    } catch (err) {
      // 后端未起时不致页面崩溃，仅留空日历
      console.error("拉取事件失败", err);
    }
  }

  useEffect(() => {
    refreshEvents();
  }, []);

  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-5">
        {/* 对话为主角：占 3 列 */}
        <section className="min-h-0 lg:col-span-3">
          <ConversationPanel
            messages={messages}
            listening={listening}
            hint="语音功能将在下个迭代接入"
            onMic={() => {}}
          />
        </section>
        {/* 日历同屏可见：占 2 列 */}
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
