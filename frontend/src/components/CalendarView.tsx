import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { CalendarEvent } from "../types";
import { downloadIcs } from "../api/client";

interface Props {
  events: CalendarEvent[];
  onEventClick?: (event: CalendarEvent) => void;
}

// 把后端事件映射为 FullCalendar 的输入结构。
function toFcEvents(events: CalendarEvent[]) {
  return events.map((e) => {
    let end = e.end_at;
    if (!end) {
      end = undefined as unknown as string;
    }
    return {
      id: String(e.id),
      title: e.title,
      start: e.start_at,
      end: end,
      extendedProps: { location: e.location, attendees: e.attendees },
    };
  });
}

/** 日历视图：展示事件，语音操作的结果会实时反映到这里；点事件看详情。 */
export default function CalendarView({ events, onEventClick }: Props) {
  function handleEventClick(arg: { event: { id: string } }) {
    if (!onEventClick) {
      return;
    }
    const id = Number(arg.event.id);
    const found = events.find((e) => e.id === id);
    if (found) {
      onEventClick(found);
    }
  }
  return (
    <div className="flex h-full flex-col border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <h2 className="font-title text-sm font-semibold tracking-wide text-fg-muted">
          日历
        </h2>
        <span className="ml-auto font-mono text-[11px] text-fg-dim">
          {events.length} 个日程
        </span>
        {/* 直接导出按钮：不需要语音，图形入口 */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => downloadIcs("week")}
            title="下载本周日历 .ics"
            className="rounded border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px] text-fg-dim transition-colors hover:border-accent-line hover:text-accent"
          >
            导出周
          </button>
          <button
            type="button"
            onClick={() => downloadIcs("month")}
            title="下载本月日历 .ics"
            className="rounded border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px] text-fg-dim transition-colors hover:border-accent-line hover:text-accent"
          >
            导出月
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 p-3">
        <FullCalendar
          plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "dayGridMonth,timeGridWeek,timeGridDay",
          }}
          locale="zh-cn"
          buttonText={{
            today: "今天",
            month: "月",
            week: "周",
            day: "日",
          }}
          height="100%"
          events={toFcEvents(events)}
          eventClick={handleEventClick}
          nowIndicator={true}
          dayMaxEvents={3}
        />
      </div>
    </div>
  );
}
