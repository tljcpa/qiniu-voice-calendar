import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import MicButton from "./MicButton";
import Waveform from "./Waveform";

interface Props {
  messages: ChatMessage[];
  listening: boolean;
  hint: string;
  busy: boolean;
  onMic: () => void;
  onSend: (text: string) => void;
}

/**
 * 对话面板：本作品的主角。展示"用户说的 + 系统语音回应"的对话流，
 * 底部录音按钮 + 录音波形 + 文字输入兜底（无障碍 / 无麦克风时可用）。
 */
export default function ConversationPanel({
  messages,
  listening,
  hint,
  busy,
  onMic,
  onSend,
}: Props) {
  const [draft, setDraft] = useState("");
  const feedRef = useRef<HTMLDivElement | null>(null);

  // 新消息自动滚到底
  useEffect(() => {
    const el = feedRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  function submit() {
    const text = draft.trim();
    if (!text || busy) {
      return;
    }
    onSend(text);
    setDraft("");
  }

  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-ink-800/60 p-4 backdrop-blur">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-neon-violet shadow-glow" />
        <h2 className="text-sm font-semibold tracking-wide text-slate-200">
          语音对话
        </h2>
        {busy && (
          <span className="ml-auto text-xs text-neon-cyan">处理中…</span>
        )}
      </div>

      {/* 对话流 */}
      <div
        ref={feedRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1"
      >
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
      </div>

      {/* 录音区 */}
      <div className="mt-4 flex flex-col items-center gap-3 border-t border-white/10 pt-4">
        <div className="flex h-12 items-center justify-center">
          {listening ? (
            <Waveform active={listening} />
          ) : (
            <p className="text-xs text-slate-400">{hint}</p>
          )}
        </div>
        <MicButton listening={listening} disabled={busy} onClick={onMic} />

        {/* 文字输入兜底 */}
        <div className="mt-1 flex w-full gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submit();
              }
            }}
            placeholder="也可以打字：明天下午三点开会"
            aria-label="文字输入指令"
            className="flex-1 rounded-xl border border-white/10 bg-ink-700/80 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-neon-cyan/50 focus:outline-none"
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-xl bg-gradient-to-br from-neon-blue to-neon-violet px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div
      className={[
        "flex animate-fadeInUp",
        isUser ? "justify-end" : "justify-start",
      ].join(" ")}
    >
      <div
        className={[
          "max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-gradient-to-br from-neon-blue to-neon-violet text-white"
            : "border border-white/10 bg-ink-700/80 text-slate-200",
          msg.interim ? "opacity-60 italic" : "",
        ].join(" ")}
      >
        {!isUser && <span className="mr-1">🤖</span>}
        {msg.text}
        {msg.events && msg.events.length > 0 && (
          <ul className="mt-2 space-y-1 border-t border-white/10 pt-2 text-xs text-neon-cyan">
            {msg.events.map((e) => (
              <li key={e.id}>
                {e.start_at.replace("T", " ").slice(5, 16)} · {e.title}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
