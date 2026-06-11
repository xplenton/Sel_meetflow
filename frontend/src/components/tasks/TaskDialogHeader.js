import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ListChecks as ListChecksIcon, Files } from 'lucide-react';
import { DialogHeader, DialogTitle } from '../ui/dialog';
import { TASK_STATUS_LABELS as STATUS_LABELS } from './taskConstants';

/**
 * TaskDialogHeader — title row of the task dialog with Entwurf/Status badge
 * and the inline "Aus Vorlage" templates picker (create mode only).
 *
 * Extracted from TaskDetailDialog during the iter 216 refactor.
 */
export default function TaskDialogHeader({
  isCreate, taskStatus,
  showTemplatePicker, onToggleTemplatePicker,
  templates, onApplyTemplate,
}) {
  return (
    <DialogHeader>
      <DialogTitle data-testid="task-dialog-title" className="flex items-center gap-2 flex-wrap">
        <ListChecksIcon className="w-4 h-4 text-[#4A5D4E]" />
        <span>Aufgabe</span>
        {isCreate ? (
          <Badge className="text-[10px] bg-[#D4A373]/15 text-[#8B6F47] ml-1">Entwurf</Badge>
        ) : taskStatus && (
          <Badge className="text-[10px] bg-[#F3F4F1] text-[#4B5563] ml-1">{STATUS_LABELS[taskStatus]}</Badge>
        )}
        {/* iter 214 — Inline-Vorlagen-Picker im Dialog (nur Create-Modus). */}
        {isCreate && (
          <div className="ml-auto relative">
            <Button type="button" size="sm" variant="outline"
              onClick={onToggleTemplatePicker}
              className="h-7 text-[11px]"
              data-testid="task-templates-inline-btn">
              <Files className="w-3 h-3 mr-1" />Aus Vorlage
            </Button>
            {showTemplatePicker && (
              <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-white border border-[#E2E4E0] rounded-lg shadow-lg overflow-hidden"
                data-testid="task-templates-picker">
                <div className="px-3 py-2 text-[10px] font-semibold text-[#6B7280] uppercase tracking-wider border-b border-[#E2E4E0]">
                  Vorlage anwenden
                </div>
                <div className="max-h-64 overflow-y-auto">
                  {templates.length === 0 ? (
                    <div className="px-3 py-3 text-[11px] text-[#9CA3AF] text-center">Keine Vorlagen vorhanden</div>
                  ) : (
                    templates.map(t => (
                      <button key={t.template_id}
                        onClick={() => onApplyTemplate(t.template_id)}
                        className="w-full text-left px-3 py-2 hover:bg-[#F5F4F0] border-b border-[#F5F4F0] last:border-0"
                        data-testid={`tpl-apply-${t.template_id}`}>
                        <div className="text-xs font-medium text-[#1A1D1B] truncate">{t.name}</div>
                        {t.title && <div className="text-[10px] text-[#9CA3AF] truncate">→ {t.title}</div>}
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </DialogTitle>
    </DialogHeader>
  );
}
