import { useState } from "react";

interface Props {
  onLogin: (username: string, password: string) => Promise<void>;
  onRegister: (username: string, password: string) => Promise<void>;
}

/**
 * 登录 / 注册页（手账风）。账户让日历数据有外部归宿、跨设备可见。
 */
export default function AuthScreen({ onLogin, onRegister }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (busy) {
      return;
    }
    if (username.trim().length < 2 || password.length < 6) {
      setErr("用户名至少 2 位，密码至少 6 位");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      if (mode === "login") {
        await onLogin(username.trim(), password);
      } else {
        await onRegister(username.trim(), password);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("401")) {
        setErr("用户名或密码错误");
      } else if (msg.includes("409")) {
        setErr("用户名已被占用");
      } else {
        setErr("操作失败，请重试");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-canvas p-4">
      <div className="w-full max-w-sm border border-line bg-panel p-6">
        <h1 className="font-title mb-1 text-2xl font-semibold text-fg">
          语音<span className="text-accent">日历</span>
        </h1>
        <p className="mb-6 text-sm text-fg-muted">
          {mode === "login" ? "登录后日程跨设备同步" : "创建账户，让日程有归处"}
        </p>

        <label className="mb-1 block text-xs text-fg-dim">用户名</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          className="mb-3 w-full rounded border border-line bg-panel2 px-3 py-2 text-sm text-fg placeholder:text-fg-dim focus:border-accent-line focus:outline-none"
          placeholder="你的用户名"
        />
        <label className="mb-1 block text-xs text-fg-dim">密码</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              submit();
            }
          }}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          className="mb-4 w-full rounded border border-line bg-panel2 px-3 py-2 text-sm text-fg placeholder:text-fg-dim focus:border-accent-line focus:outline-none"
          placeholder="至少 6 位"
        />

        {err && <p className="mb-3 text-sm text-danger">{err}</p>}

        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="font-title w-full rounded border border-accent-line bg-accent-soft py-2 text-sm font-medium text-accent transition-colors hover:bg-accent hover:text-canvas disabled:opacity-50"
        >
          {busy ? "请稍候…" : mode === "login" ? "登录" : "注册"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setErr(null);
          }}
          className="mt-4 w-full text-center text-xs text-fg-muted hover:text-fg"
        >
          {mode === "login" ? "没有账户？去注册" : "已有账户？去登录"}
        </button>
      </div>
    </div>
  );
}
