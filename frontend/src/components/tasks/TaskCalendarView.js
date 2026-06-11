/* Simple month/week/day calendar view for tasks (iter 192).
   Lightweight - uses CSS grid; no external date library. */
import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '../ui/button';

const PRIO_COLOR = {
  urgent: 'bg-[#C87967]',
  high: 'bg-[#D4A373]',
  normal: 'bg-[#4A5D4E]',
  low: 'bg-[#9CA3AF]',
};

export default function TaskCalendarView({ tasks, onOpen }) {
  const [view, setView] = useState('month'); // month | week | day | workweek
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });

  const tasksByDay = useMemo(() => {
    const map = {};
    tasks.forEach(t => {
      if (!t.due_date) return;
      const key = String(t.due_date).split('T')[0];
      (map[key] = map[key] || []).push(t);
    });
    return map;
  }, [tasks]);

  const fmtKey = (d) => d.toISOString().split('T')[0];

  const renderDay = (day) => {
    const k = fmtKey(day);
    const items = tasksByDay[k] || [];
    return (
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-3 min-h-[200px]" data-testid={`cal-day-${k}`}>
        <div className="text-xs uppercase tracking-wider text-[#9CA3AF] mb-2">
          {day.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}
        </div>
        <div className="space-y-1.5">
          {items.length === 0 && <p className="text-[11px] text-[#9CA3AF]">Keine Aufgaben.</p>}
          {items.map(t => (
            <button key={t.task_id}
              data-testid={`cal-task-${t.task_id}`}
              onClick={() => onOpen(t.task_id)}
              className={`w-full text-left text-xs px-2 py-1.5 rounded-lg ${PRIO_COLOR[t.priority] || PRIO_COLOR.normal} text-white hover:opacity-90`}>
              <div className="font-medium truncate">{t.title}</div>
              <div className="text-[10px] opacity-80">{t.status}</div>
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderMonth = () => {
    const year = cursor.getFullYear(), month = cursor.getMonth();
    const first = new Date(year, month, 1);
    const start = new Date(first);
    start.setDate(1 - ((first.getDay() + 6) % 7));  // Monday start
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      cells.push(d);
    }
    return (
      <div className="grid grid-cols-7 gap-1">
        {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map(d =>
          <div key={d} className="text-[10px] uppercase tracking-wider text-[#9CA3AF] text-center py-1">{d}</div>
        )}
        {cells.map((d, i) => {
          const k = fmtKey(d);
          const items = tasksByDay[k] || [];
          const inMonth = d.getMonth() === month;
          const isToday = fmtKey(d) === fmtKey(new Date());
          return (
            <div key={i}
              className={`bg-white border border-[#E2E4E0] rounded-lg p-1.5 min-h-[80px] ${!inMonth ? 'opacity-40' : ''} ${isToday ? 'ring-2 ring-[#4A5D4E]' : ''}`}>
              <div className="text-[10px] text-[#6B7280] mb-1">{d.getDate()}</div>
              <div className="space-y-0.5">
                {items.slice(0, 3).map(t => (
                  <button key={t.task_id}
                    onClick={() => onOpen(t.task_id)}
                    className={`block w-full text-left text-[9px] px-1.5 py-0.5 rounded ${PRIO_COLOR[t.priority] || PRIO_COLOR.normal} text-white truncate`}>
                    {t.title}
                  </button>
                ))}
                {items.length > 3 && <span className="text-[9px] text-[#9CA3AF]">+{items.length - 3} weitere</span>}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const moveCursor = (delta) => {
    const d = new Date(cursor);
    if (view === 'day') d.setDate(d.getDate() + delta);
    else if (view === 'week' || view === 'workweek') d.setDate(d.getDate() + 7 * delta);
    else d.setMonth(d.getMonth() + delta);
    setCursor(d);
  };

  const renderWeek = (workweek = false) => {
    const start = new Date(cursor);
    start.setDate(cursor.getDate() - ((cursor.getDay() + 6) % 7));
    const days = Array.from({ length: workweek ? 5 : 7 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
    return <div className={`grid grid-cols-1 sm:grid-cols-${workweek ? '5' : '7'} gap-2`}>{days.map(d => <div key={d.toISOString()}>{renderDay(d)}</div>)}</div>;
  };

  return (
    <div data-testid="task-calendar-view">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => moveCursor(-1)} className="h-8 w-8 p-0"><ChevronLeft className="w-4 h-4" /></Button>
          <Button variant="outline" size="sm" onClick={() => setCursor(new Date())} className="h-8 px-3 text-xs">Heute</Button>
          <Button variant="outline" size="sm" onClick={() => moveCursor(1)} className="h-8 w-8 p-0"><ChevronRight className="w-4 h-4" /></Button>
          <span className="text-sm font-medium text-[#1C1F1D] ml-2">
            {view === 'month'
              ? cursor.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })
              : cursor.toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })}
          </span>
        </div>
        <div className="flex bg-[#F3F4F1] rounded-lg p-0.5">
          {['day', 'workweek', 'week', 'month'].map(v => (
            <button key={v}
              data-testid={`cal-view-${v}`}
              onClick={() => setView(v)}
              className={`px-3 py-1 text-xs rounded-md ${view === v ? 'bg-white shadow-sm font-medium' : 'text-[#6B7280]'}`}>
              {{ day: 'Tag', workweek: 'Arbeitswoche', week: 'Woche', month: 'Monat' }[v]}
            </button>
          ))}
        </div>
      </div>

      {view === 'month' && renderMonth()}
      {view === 'week' && renderWeek(false)}
      {view === 'workweek' && renderWeek(true)}
      {view === 'day' && renderDay(cursor)}
    </div>
  );
}
