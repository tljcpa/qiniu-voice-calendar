interface Props {
  listening: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/**
 * 录音按钮：克制方案——常态硬线描边，录音时填强调色 + 细环（无渐变无霓虹光晕）。
 */
export default function MicButton({ listening, disabled, onClick }: Props) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={listening ? "停止录音" : "开始录音"}
      className={[
        "flex h-11 w-11 items-center justify-center rounded-full border transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        listening
          ? "border-accent bg-accent text-canvas ring-2 ring-accent/30"
          : "border-line bg-panel2 text-fg-muted hover:border-accent-line hover:text-fg",
      ].join(" ")}
    >
      <MicIcon />
    </button>
  );
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <rect
        x="9"
        y="3"
        width="6"
        height="11"
        rx="3"
        fill="currentColor"
      />
      <path
        d="M5 11a7 7 0 0 0 14 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M12 18v3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
