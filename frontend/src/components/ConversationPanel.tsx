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
 * 对话面板：作品主交互。展示"用户说的 + 系统回应"的对话流，
 * 底部录音按钮 + 波形 + 文字输入兜底。克制专业、高密度、无 emoji 无渐变。
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
    <div className="flex h-full flex-col border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
          对话
        </h2>
        <span className="font-mono text-[11px] text-fg-dim">
          {listening ? "录音中" : busy ? "处理中" : "就绪"}
        </span>
      </div>

      {/* 对话流 */}
      <div
        ref={feedRef}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4"
      >
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
      </div>

      {/* 录音 + 输入区 */}
      <div className="border-t border-line px-4 py-3">
        <div className="mb-3 flex items-center gap-3">
          <MicButton listening={listening} disabled={busy} onClick={onMic} />
          <div className="flex h-7 flex-1 items-center">
            {listening ? (
              <Waveform active={listening} />
            ) : (
              <span className="font-mono text-[11px] text-fg-dim">{hint}</span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submit();
              }
            }}
            placeholder="输入指令，例如：明天下午三点开会"
            aria-label="文字输入指令"
            className="flex-1 rounded border border-line bg-panel2 px-3 py-1.5 text-sm text-fg placeholder:text-fg-dim focus:border-accent-line focus:outline-none"
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded border border-accent-line bg-accent-soft px-4 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent hover:text-canvas disabled:opacity-40"
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
    <div className="animate-fadeIn">
      {/* 角色标签：mono 小字替代 emoji */}
      <div
        className={[
          "mb-1 font-mono text-[10px] uppercase tracking-wider",
          isUser ? "text-right text-fg-dim" : "text-left text-accent",
        ].join(" ")}
      >
        {isUser ? "你" : "助手"}
      </div>
      <div className={isUser ? "flex justify-end" : "flex justify-start"}>
        <div
          className={[
            "max-w-[85%] rounded border px-3 py-2 text-sm leading-relaxed",
            isUser
              ? "border-line bg-panel2 text-fg"
              : "border-accent-line/50 bg-accent-soft/40 text-fg",
            msg.interim ? "italic text-fg-muted" : "",
          ].join(" ")}
        >
          {msg.text}
          {msg.events && msg.events.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-line pt-2">
              {msg.events.map((e) => (
                <li
                  key={e.id}
                  className="flex items-baseline gap-2 font-mono text-[11px]"
                >
                  <span className="text-accent">
                    {e.start_at.replace("T", " ").slice(5, 16)}
                  </span>
                  <span className="text-fg-muted">{e.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
