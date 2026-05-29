import type { ChatMessage } from "../types";
import MicButton from "./MicButton";

interface Props {
  messages: ChatMessage[];
  listening: boolean;
  hint: string;
  onMic: () => void;
}

/**
 * 对话面板：本作品的主角。展示"用户说的 + 系统语音回应"的对话流，
 * 底部是录音按钮。让评委一眼看到"语音交互闭环"。
 */
export default function ConversationPanel({
  messages,
  listening,
  hint,
  onMic,
}: Props) {
  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-ink-800/60 p-4 backdrop-blur">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-neon-violet shadow-glow" />
        <h2 className="text-sm font-semibold tracking-wide text-slate-200">
          语音对话
        </h2>
      </div>

      {/* 对话流 */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
      </div>

      {/* 录音区 */}
      <div className="mt-4 flex flex-col items-center gap-2 border-t border-white/10 pt-4">
        <MicButton listening={listening} onClick={onMic} />
        <p className="text-xs text-slate-400">{hint}</p>
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
