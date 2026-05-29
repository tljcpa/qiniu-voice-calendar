import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { CalendarEvent } from "../types";

interface Props {
  events: CalendarEvent[];
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

/** 日历视图：展示事件，语音操作的结果会实时反映到这里。 */
export default function CalendarView({ events }: Props) {
  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-ink-800/60 p-4 backdrop-blur">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-neon-cyan shadow-glow" />
        <h2 className="text-sm font-semibold tracking-wide text-slate-200">
          我的日历
        </h2>
        <span className="ml-auto text-xs text-slate-500">
          共 {events.length} 个日程
        </span>
      </div>
      <div className="min-h-0 flex-1">
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
          nowIndicator={true}
          dayMaxEvents={3}
        />
      </div>
    </div>
  );
}
