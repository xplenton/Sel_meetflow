import TaskCard from './TaskCard';

export default function TaskBoard({ tasks, statusLabels, onOpen, onStatusChange, users = [] }) {
  const cols = Object.keys(statusLabels);
  const grouped = cols.reduce((acc, st) => {
    acc[st] = tasks.filter(t => t.status === st);
    return acc;
  }, {});
  const userMap = users.reduce((a, u) => { a[u.user_id] = u; return a; }, {});

  // Native HTML5 drag-and-drop
  const onDragStart = (e, taskId) => { e.dataTransfer.setData('text/plain', taskId); };
  const onDrop = (e, status) => {
    e.preventDefault();
    const tid = e.dataTransfer.getData('text/plain');
    if (tid) onStatusChange(tid, status);
  };
  const onDragOver = (e) => e.preventDefault();

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="task-board">
      {cols.map(st => (
        <div key={st}
          onDrop={(e) => onDrop(e, st)} onDragOver={onDragOver}
          data-testid={`board-col-${st}`}
          className="bg-[#F3F4F1] border border-[#E2E4E0] rounded-xl p-3 min-h-[300px]">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">{statusLabels[st]}</h3>
            <span className="text-[10px] text-[#9CA3AF]">{grouped[st].length}</span>
          </div>
          <div className="space-y-2">
            {grouped[st].map(t => (
              <div key={t.task_id} draggable onDragStart={(e) => onDragStart(e, t.task_id)}>
                <TaskCard task={t} onOpen={onOpen} userMap={userMap} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
