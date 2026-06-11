import { useState } from 'react';
import { Button } from '../ui/button';
import { Trash2, Copy, Loader2, MoreVertical } from 'lucide-react';

/**
 * TaskFooter — sticky footer with primary cluster (Abbrechen + Speichern)
 * and secondary actions (Duplizieren / Löschen) shown as inline buttons on
 * desktop and a kebab menu on mobile.
 *
 * Extracted from TaskDetailDialog during the iter 216 refactor.
 */
export default function TaskFooter({
  isCreate, creating, canDelete,
  hasTitle,
  onCancel, onSave, onDuplicate, onDelete,
  onBlockBlurAutosave,
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-[#E2E4E0] sticky bottom-0 bg-white">
      {/* Primary cluster (Abbrechen + Speichern) — always together */}
      <div className="flex items-stretch gap-2 w-full sm:w-auto">
        <Button
          onMouseDown={onBlockBlurAutosave}
          onClick={onCancel}
          variant="outline" size="sm"
          className="flex-1 sm:flex-initial h-9 text-xs border-[#C87967]/40 text-[#C87967] hover:bg-[#C87967]/5 hover:text-[#C87967]"
          data-testid="task-cancel-button"
          disabled={creating}>
          Abbrechen
        </Button>
        <Button
          onMouseDown={onBlockBlurAutosave}
          onClick={onSave}
          size="sm"
          className="flex-1 sm:flex-initial bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-9 text-xs whitespace-nowrap"
          data-testid="task-close-save-button"
          disabled={creating || (isCreate && !hasTitle)}>
          <span className="sm:inline">Speichern</span>
          <span className="hidden sm:inline">&nbsp;und schließen</span>
        </Button>
      </div>

      {isCreate && creating && (
        <span data-testid="task-autosave-hint" className="text-[11px] text-[#9CA3AF] flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" />Wird gespeichert ...
        </span>
      )}

      {/* Secondary actions: only when editing an existing task */}
      {!isCreate && (
        <div className="ml-auto flex items-center gap-2 w-full sm:w-auto justify-end">
          {/* Mobile: kebab menu */}
          <div className="sm:hidden relative">
            <Button variant="outline" size="sm" className="h-9 px-2 text-xs"
              onClick={() => setMenuOpen(v => !v)}
              data-testid="task-secondary-menu-btn">
              <MoreVertical className="w-3.5 h-3.5" />
            </Button>
            {menuOpen && (
              <div className="absolute right-0 bottom-full mb-1 z-50 w-44 bg-white border border-[#E2E4E0] rounded-lg shadow-lg overflow-hidden"
                data-testid="task-secondary-menu">
                <button onClick={() => { setMenuOpen(false); onDuplicate(); }}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-[#F5F4F0] flex items-center gap-2"
                  data-testid="task-duplicate-button-mobile">
                  <Copy className="w-3.5 h-3.5" />Duplizieren
                </button>
                {canDelete && (
                  <button onClick={() => { setMenuOpen(false); onDelete(); }}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-[#C87967]/10 text-[#C87967] flex items-center gap-2 border-t border-[#E2E4E0]"
                    data-testid="task-delete-button-mobile">
                    <Trash2 className="w-3.5 h-3.5" />Löschen
                  </button>
                )}
              </div>
            )}
          </div>
          {/* Desktop: inline buttons */}
          <Button data-testid="task-duplicate-button" variant="outline" size="sm"
            onClick={onDuplicate} className="hidden sm:inline-flex h-9 text-xs">
            <Copy className="w-3 h-3 mr-1" />Duplizieren
          </Button>
          {canDelete && (
            <Button data-testid="task-delete-button" variant="outline" size="sm" onClick={onDelete}
              className="hidden sm:inline-flex h-9 text-xs border-[#C87967]/40 text-[#C87967] hover:bg-[#C87967]/5 hover:text-[#C87967]">
              <Trash2 className="w-3 h-3 mr-1" />Löschen
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
