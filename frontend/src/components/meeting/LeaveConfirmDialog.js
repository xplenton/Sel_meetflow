import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { LogOut } from 'lucide-react';

/**
 * Small confirmation dialog shown before the user actually leaves the
 * meeting. Extracted from LiveMeetingPage (iter 215 refactor).
 */
export default function LeaveConfirmDialog({ open, onOpenChange, isRecording, onConfirm }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm" data-testid="leave-confirm-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <LogOut className="w-4 h-4 text-[#C87967]" />Meeting verlassen?
          </DialogTitle>
          <DialogDescription className="text-xs text-[#9CA3AF]">
            Sind Sie sicher, dass Sie das Meeting verlassen möchten?
            {isRecording && ' Die Aufnahme wird gestoppt.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 justify-end mt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}
            className="text-xs h-8" data-testid="leave-cancel-btn">Abbrechen</Button>
          <Button size="sm" onClick={() => { onOpenChange(false); onConfirm(); }}
            className="bg-[#C87967] hover:bg-[#B5685A] text-white text-xs h-8" data-testid="leave-confirm-btn">
            <LogOut className="w-3.5 h-3.5 mr-1" />Verlassen
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
