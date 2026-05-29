interface Props {
  listening: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/**
 * 录音按钮：科技感圆形按钮，监听时外圈脉冲扩散动画。
 * PR10 为视觉骨架（onClick 占位），PR11 接 Azure Speech 流式识别。
 */
export default function MicButton({ listening, disabled, onClick }: Props) {
  return (
    <div className="relative flex items-center justify-center">
      {listening && (
        <>
          <span className="absolute h-20 w-20 rounded-full bg-neon-cyan/30 animate-pulseRing" />
          <span
            className="absolute h-20 w-20 rounded-full bg-neon-cyan/20 animate-pulseRing"
            style={{ animationDelay: "0.6s" }}
          />
        </>
      )}
      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        aria-label={listening ? "停止录音" : "开始录音"}
        className={[
          "relative flex h-16 w-16 items-center justify-center rounded-full transition-all",
          "disabled:cursor-not-allowed disabled:opacity-40",
          listening
            ? "bg-gradient-to-br from-neon-cyan to-neon-blue shadow-glow-lg scale-105"
            : "bg-gradient-to-br from-ink-600 to-ink-700 hover:shadow-glow hover:scale-105 border border-white/10",
        ].join(" ")}
      >
        <MicIcon active={listening} />
      </button>
    </div>
  );
}

function MicIcon({ active }: { active: boolean }) {
  const color = active ? "#0a0e1a" : "#22d3ee";
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
      <rect x="9" y="3" width="6" height="11" rx="3" fill={color} />
      <path
        d="M5 11a7 7 0 0 0 14 0"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M12 18v3" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
