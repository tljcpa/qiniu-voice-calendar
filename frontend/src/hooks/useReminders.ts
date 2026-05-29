// 提醒轮询 hook：定时拉取到期提醒并弹浏览器通知（见复盘 D-09）。
//
// 浏览器通知需用户授权；首次调用 enable() 申请权限。轮询而非 WebSocket：
// 实现简单、DB 即状态、浏览器一打开就能补弹错过的提醒。
import { useEffect, useRef, useState } from "react";

interface DueReminder {
  id: number;
  title: string;
  start_at: string;
  remind_at: string;
}

const POLL_MS = 30000; // 30 秒轮询一次

export function useReminders() {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "denied"
  );
  const timerRef = useRef<number | null>(null);

  async function enable() {
    if (typeof Notification === "undefined") {
      return;
    }
    const p = await Notification.requestPermission();
    setPermission(p);
  }

  useEffect(() => {
    // 仅在已授权时才轮询。否则 /due 会把到期提醒标记已发却无法弹出，
    // 导致授权前到期的提醒被静默消费、永久丢失。
    if (permission !== "granted") {
      return;
    }

    async function poll() {
      try {
        const resp = await fetch("/api/reminders/due");
        if (!resp.ok) {
          return;
        }
        const due: DueReminder[] = await resp.json();
        for (const r of due) {
          showNotification(r);
        }
      } catch {
        // 静默失败，下次轮询再试
      }
    }

    function showNotification(r: DueReminder) {
      const timeStr = r.start_at.replace("T", " ").slice(5, 16);
      new Notification("日程提醒", {
        body: `${timeStr} · ${r.title}`,
      });
    }

    // 立即拉一次 + 定时轮询
    poll();
    timerRef.current = window.setInterval(poll, POLL_MS);
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [permission]);

  return { permission, enable };
}
