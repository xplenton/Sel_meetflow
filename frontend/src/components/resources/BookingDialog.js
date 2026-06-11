import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Loader2 } from 'lucide-react';
import DayTimelinePreview from './DayTimelinePreview';
import BookingCateringSection from './BookingCateringSection';
import BookingSeriesSection from './BookingSeriesSection';
import BookingFloorplanView from './BookingFloorplanView';
import useBookingDialog from './bookingDialog/useBookingDialog';
import BookingResourceHeader from './bookingDialog/BookingResourceHeader';
import { BookingForUserPicker } from './bookingDialog/BookingTargetSelectors';
import BookingDateTimeFields from './bookingDialog/BookingDateTimeFields';
import BookingConflictsPanel from './bookingDialog/BookingConflictsPanel';
import BookingComboSection from './bookingDialog/BookingComboSection';
import BookingAdvancedDetails from './bookingDialog/BookingAdvancedDetails';

/**
 * Anwender-freundlicher Buchungs-Dialog.
 * Refactored iter 302: state + side-effects moved to useBookingDialog,
 * UI split into focused sub-components under ./bookingDialog/.
 */
export default function BookingDialog({ resource, onClose }) {
  const h = useBookingDialog(resource, onClose);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[90vh] overflow-y-auto" data-testid="booking-dialog">
        <DialogHeader>
          <DialogTitle>Buchung anlegen</DialogTitle>
          <DialogDescription>
            Prüfe Verfügbarkeit live und nutze Quick-Buttons für Datum &amp; Dauer.
          </DialogDescription>
        </DialogHeader>

        <BookingResourceHeader resource={resource} />
        <BookingFloorplanView resource={resource} />

        <BookingForUserPicker
          bookableUsers={h.bookableUsers}
          bookedForUserId={h.bookedForUserId}
          onChange={h.setBookedForUserId}
        />

        {/* Iter 343 — `BookingTargetPicker` entfernt: Bereich-Auswahl
            erfolgt jetzt ausschließlich in der Kombi-Sektion unten (auch bei
            Einzelauswahl). Vermeidet redundante UI an zwei Stellen. */}

        <div>
          <Label>Titel <span className="text-rose-600">*</span></Label>
          <Input data-testid="booking-title-input" value={h.title}
                 onChange={e => h.setTitle(e.target.value)}
                 placeholder="z.B. Wochenbesprechung Team Innere" autoFocus />
        </div>

        <BookingDateTimeFields
          start={h.start}
          end={h.end}
          durationMin={h.durationMin}
          onStart={h.setStart}
          onEnd={h.setEnd}
          onSetQuickDate={h.setQuickDate}
          onSetDuration={h.setDuration}
        />

        {h.target && h.start && h.end && (
          <DayTimelinePreview
            resourceId={h.target}
            startISO={new Date(h.start).toISOString()}
            endISO={new Date(h.end).toISOString()}
            hasConflict={h.conflicts.length > 0}
          />
        )}

        <BookingConflictsPanel
          checking={h.checking}
          conflicts={h.conflicts}
          suggestions={h.suggestions}
          start={h.start}
          end={h.end}
          onAcceptSuggestion={h.acceptSuggestion}
          targets={h.targets}
          currentTarget={h.target}
          onSwitchTarget={h.setTarget}
          onForceSubmitPending={() => h.submit({ allowPendingOverlap: true })}
        />

        <BookingComboSection
          resource={resource}
          comboSubs={h.comboSubs}
          onChange={h.setComboSubs}
          availability={h.targetAvailability}
        />

        {h.allowCatering && (
          <BookingCateringSection
            enabled={h.cateringEnabled}
            onToggle={() => h.setCateringEnabled(v => !v)}
            items={h.cateringItems}
            availableItems={h.availableItems}
            onAddLine={h.addCateringLine}
            onUpdateLine={h.updateLine}
            onRemoveLine={h.removeLine}
            total={h.cateringTotal}
            totalQty={h.totalQty}
            attachments={h.cateringAttachments}
            onAttachmentsChange={h.setCateringAttachments}
            leadTimeWarning={h.leadTimeWarning}
          />
        )}

        <BookingSeriesSection
          enabled={h.seriesEnabled}
          onToggle={() => h.setSeriesEnabled(v => !v)}
          recurrence={h.seriesRecurrence}
          onRecurrenceChange={h.setSeriesRecurrence}
          occurrences={h.seriesOccurrences}
          onOccurrencesChange={h.setSeriesOccurrences}
          customDates={h.seriesCustomDates}
          onCustomDatesChange={h.setSeriesCustomDates}
        />

        <BookingAdvancedDetails
          resource={resource}
          showAdvanced={h.showAdvanced}
          onToggle={() => h.setShowAdvanced(v => !v)}
          costCenter={h.costCenter} onCostCenter={h.setCostCenter}
          account={h.account} onAccount={h.setAccount}
          costCenters={h.costCenters} accounts={h.accounts}
          destination={h.destination} onDestination={h.setDestination}
          mileageBefore={h.mileageBefore} onMileageBefore={h.setMileageBefore}
          purpose={h.purpose} onPurpose={h.setPurpose}
        />

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="ghost" onClick={() => onClose(false)} data-testid="booking-cancel">Abbrechen</Button>
          <div className="flex-1" />
          {h.disabledReason && (
            <span className="text-[10px] text-[#9CA3AF] self-center" data-testid="booking-disabled-hint">
              {h.disabledReason}
            </span>
          )}
          <Button onClick={h.submit}
            data-testid="booking-submit"
            disabled={h.submitting || h.checking || !!h.disabledReason}
            title={h.disabledReason || ''}>
            {h.submitting && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {h.seriesEnabled
              ? `${h.seriesOccurrences || 4} Serie-Termine anlegen`
              : (resource.requires_approval ? 'Buchung beantragen' : 'Jetzt buchen')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
