// Gemeinsame Konstanten für das Task-Modul (iter 194).
// Status-Key 'blocked' bleibt für Backward-Compat in der DB; das deutsche
// Label heißt jetzt "Wartend" laut User-Wunsch.

export const TASK_STATUS_LABELS = {
  open: 'Offen',
  in_progress: 'In Bearbeitung',
  blocked: 'Wartend',
  done: 'Erledigt',
};

export const TASK_PRIORITY_LABELS = {
  low: 'Niedrig',
  normal: 'Normal',
  high: 'Hoch',
  urgent: 'Dringend',
};

export const TASK_STATUSES = ['open', 'in_progress', 'blocked', 'done'];
export const TASK_PRIORITIES = ['low', 'normal', 'high', 'urgent'];

export const STATUS_COLOR = {
  open: 'bg-blue-50 text-blue-700',
  in_progress: 'bg-amber-50 text-amber-700',
  blocked: 'bg-orange-50 text-orange-700',
  done: 'bg-emerald-50 text-emerald-700',
};

export const PRIORITY_BADGE = {
  urgent: 'bg-[#C87967] text-white',
  high: 'bg-[#D4A373] text-white',
  normal: 'bg-[#E2E4E0] text-[#4A5D4E]',
  low: 'bg-[#F3F4F1] text-[#9CA3AF]',
};
