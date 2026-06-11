import { Label } from '../../ui/label';
import { CheckCircle2, Clock, AlertCircle } from 'lucide-react';

/**
 * BookingComboSection (iter 343) — Single source of truth for sub-room
 * selection on splittable rooms. Replaces the redundant BookingTargetPicker
 * dropdown. Behaviour:
 *   - 0 selected   → book the parent (whole room).
 *   - 1 selected   → book that sub-room only.
 *   - >=2 selected → kombi-booking (the submit flow detects this and POSTs
 *                    to /resource-bookings/combo).
 *
 * Verfügbarkeits-Indikator (✅ / ⏳ / ⛔) ist direkt auf jedem Chip sichtbar,
 * abgeleitet aus dem gleichen `targetAvailability`-Map wie zuvor das
 * Dropdown.
 */
export default function BookingComboSection({ resource, comboSubs, onChange, availability }) {
  if (!(resource.is_splitable && (resource.children || []).length > 1)) return null;
  const children = resource.children || [];
  const parentId = resource.resource_id;

  const toggle = (subId) => {
    onChange(comboSubs.includes(subId)
      ? comboSubs.filter(s => s !== subId)
      : [...comboSubs, subId]);
  };
  const selectAll = () => onChange(children.map(c => c.sub_id));
  const clearAll = () => onChange([]);

  const fmtTime = (iso) => {
    try { return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); }
    catch { return ''; }
  };
  const subAvailability = (sub) => {
    // Match availability by resource_id (children carry their own resource_id)
    const childRid = sub.resource_id || sub.sub_id;
    const a = availability?.[childRid];
    if (!a || a.state === 'unknown') return { icon: null, text: '' };
    if (a.state === 'free') return { icon: <CheckCircle2 className="w-3 h-3" />, text: 'frei', tone: 'free' };
    const conflict = a.conflicts?.[0];
    const allPending = a.conflicts?.every(c => c.status === 'pending_approval');
    if (allPending) {
      return {
        icon: <Clock className="w-3 h-3" />,
        text: conflict ? `pending ${fmtTime(conflict.start_at)}` : 'pending',
        tone: 'pending',
      };
    }
    return {
      icon: <AlertCircle className="w-3 h-3" />,
      text: conflict ? `belegt ${fmtTime(conflict.start_at)}` : 'belegt',
      tone: 'busy',
    };
  };
  // Parent availability — chip-style preview for "ganzer Raum"
  const parentAvail = subAvailability({ resource_id: parentId, sub_id: '__parent__' });

  return (
    <div className="border border-[#E2E4E0] rounded-lg p-3 bg-[#FAFBF9] space-y-2" data-testid="booking-combo-section">
      <div className="flex items-center justify-between">
        <Label className="text-xs">Bereich auswählen</Label>
        <div className="flex gap-1">
          <button type="button" onClick={clearAll} className="text-[10px] underline text-[#6B7280] hover:text-[#1C1F1D]" data-testid="combo-select-parent">
            Ganzer Raum
          </button>
          <span className="text-[10px] text-[#6B7280]">·</span>
          <button type="button" onClick={selectAll} className="text-[10px] underline text-[#6B7280] hover:text-[#1C1F1D]" data-testid="combo-select-all">
            Alle Teilbereiche
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {children.map(c => {
          const active = comboSubs.includes(c.sub_id);
          const av = subAvailability(c);
          const toneClass = av.tone === 'busy'
            ? 'ring-1 ring-rose-200'
            : av.tone === 'pending' ? 'ring-1 ring-amber-200' : '';
          return (
            <button type="button" key={c.sub_id}
              onClick={() => toggle(c.sub_id)}
              data-testid={`combo-sub-${c.sub_id}`}
              className={`px-3 py-1.5 rounded-full border text-xs inline-flex items-center gap-1.5 ${active
                ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]'
                : 'bg-white text-[#1C1F1D] border-[#E2E4E0]'} ${toneClass}`}
              title={av.text || ''}
            >
              <span>Bereich {c.sub_id}</span>
              {av.icon && (
                <span className={
                  av.tone === 'free' ? (active ? 'text-emerald-200' : 'text-emerald-600')
                  : av.tone === 'pending' ? (active ? 'text-amber-200' : 'text-amber-600')
                  : (active ? 'text-rose-200' : 'text-rose-600')
                }>
                  {av.icon}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="text-[10px] text-[#6B7280]">
        {comboSubs.length === 0 && (
          <>Gesamter Raum (Parent) wird gebucht{parentAvail.text ? ` · ${parentAvail.text}` : ''}.</>
        )}
        {comboSubs.length === 1 && (
          <>Einzelner Teilbereich {comboSubs[0]} wird gebucht.</>
        )}
        {comboSubs.length >= 2 && (
          <span className="text-amber-700">Kombi-Buchung aktiv: {comboSubs.join(' + ')}</span>
        )}
      </div>
    </div>
  );
}
