import type { CalendarEvent } from "../types";

interface Props {
  event: CalendarEvent;
  onClose: () => void;
  onDelete: (event: CalendarEvent) => void;
}

function fmtRange(startIso: string, endIso: string | null): string {
  const start = startIso.replace("T", " ").slice(0, 16);
  if (!endIso) {
    return start;
  }
  // 同日只显示结束时分
  const sameDay = startIso.slice(0, 10) === endIso.slice(0, 10);
  const end = sameDay ? endIso.slice(11, 16) : endIso.replace("T", " ").slice(0, 16);
  return `${start} – ${end}`;
}

/**
 * 事件详情模态：点日历事件弹出，展示信息并可删除（图形化管理，补充语音）。
 * 克制实底面板（非毛玻璃），硬线边框，时间用 mono。
 */
export default function EventDetail({ event, onClose, onDelete }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#120e09]/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm border border-line bg-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h3 className="font-title text-sm font-semibold tracking-wide text-fg-muted">
            事件详情
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="text-fg-dim hover:text-fg"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M6 6l12 12M18 6L6 18"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          <div className="font-title text-lg font-medium text-fg">{event.title}</div>
          <Row label="时间" value={fmtRange(event.start_at, event.end_at)} mono />
          {event.location && <Row label="地点" value={event.location} />}
          {event.attendees.length > 0 && (
            <Row label="参与人" value={event.attendees.join("、")} />
          )}
          {event.note && <Row label="备注" value={event.note} />}
        </div>

        <div className="flex justify-end gap-2 border-t border-line px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line bg-panel2 px-3 py-1.5 text-sm text-fg-muted hover:text-fg"
          >
            关闭
          </button>
          <button
            type="button"
            onClick={() => onDelete(event)}
            className="rounded border border-danger/50 px-3 py-1.5 text-sm text-danger hover:bg-danger hover:text-canvas"
          >
            删除
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-12 shrink-0 text-fg-dim">{label}</span>
      <span className={mono ? "font-mono text-fg" : "text-fg"}>{value}</span>
    </div>
  );
}
