import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { Flag } from 'lucide-react';

/**
 * Reusable Report/Melden dialog.
 * target: { type: 'post'|'comment'|'question', id, label } | null
 */
export default function ReportContentDialog({ target, reason, onReasonChange, onCancel, onSubmit, isDE = true }) {
  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="text-base font-medium flex items-center gap-2">
            <Flag className="w-4 h-4 text-[#C87967]" />
            {isDE ? 'Inhalt melden' : 'Report content'}
          </DialogTitle>
          <DialogDescription className="text-xs text-[#6B7280]">
            {isDE ? 'Warum moechtest du diesen Inhalt melden? Dein Hinweis wird an die Moderation weitergeleitet.'
                  : 'Why do you want to report this content? Your report will be reviewed by moderators.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          {target?.label && (
            <div className="p-2 bg-[#F3F4F1] rounded-lg text-xs text-[#6B7280] line-clamp-2">"{target.label}"</div>
          )}
          <textarea value={reason} onChange={e => onReasonChange(e.target.value)}
            placeholder={isDE ? 'Grund beschreiben (z.B. beleidigend, Spam, Datenschutz...)' : 'Describe reason...'}
            className="w-full min-h-[90px] p-3 border border-[#E2E4E0] rounded-xl text-sm resize-y focus:outline-none focus:border-[#4A5D4E]"
            data-testid="report-reason-input" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} className="rounded-full border-[#E2E4E0]">
            {isDE ? 'Abbrechen' : 'Cancel'}
          </Button>
          <Button onClick={onSubmit} className="bg-[#C87967] hover:bg-[#B56555] text-white rounded-full" data-testid="submit-report-btn">
            {isDE ? 'Melden' : 'Report'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
