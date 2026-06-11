import { useEffect, useMemo, useState } from 'react';
import api from '../../../lib/api';
import { toast } from 'sonner';
import { defaultStart, defaultEnd, toLocal } from './bookingHelpers';
import {
  fetchCateringItems, fetchCostCenters, fetchAccounts, fetchBookableUsers,
} from '../../../lib/bookingRefdataCache';

/**
 * Encapsulates all state, side-effects and submit logic for BookingDialog
 * (extracted iter 302 — keeps the dialog component focused on layout).
 */
export default function useBookingDialog(resource, onClose) {
  const [target, setTarget] = useState(resource.resource_id);
  const [title, setTitle] = useState('');
  const [start, setStart] = useState(defaultStart());
  const [end, setEnd] = useState(defaultEnd());
  const [purpose, setPurpose] = useState('');
  const [destination, setDestination] = useState('');
  const [mileageBefore, setMileageBefore] = useState('');
  const [costCenter, setCostCenter] = useState('');
  const [account, setAccount] = useState('');
  const [cateringEnabled, setCateringEnabled] = useState(false);
  const [cateringItems, setCateringItems] = useState([]);
  const [cateringAttachments, setCateringAttachments] = useState([]);
  const [availableItems, setAvailableItems] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [comboSubs, setComboSubs] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [seriesEnabled, setSeriesEnabled] = useState(false);
  const [seriesRecurrence, setSeriesRecurrence] = useState('weekly');
  const [seriesOccurrences, setSeriesOccurrences] = useState(4);
  // Iter 334 — Liste expliziter Datums-Auswahlen für recurrence='custom'.
  const [seriesCustomDates, setSeriesCustomDates] = useState([]);
  const [bookableUsers, setBookableUsers] = useState([]);
  const [bookedForUserId, setBookedForUserId] = useState('');
  // Iter 339 — Issue #3: availability indicator per target (parent + subs).
  // Map { resource_id -> { state: 'free'|'busy'|'unknown', conflicts: [...] } }
  const [targetAvailability, setTargetAvailability] = useState({});

  const targets = useMemo(() => {
    const list = [{ id: resource.resource_id, name: resource.name + (resource.is_splitable ? ' (komplett)' : '') }];
    (resource.children || []).forEach(c => list.push({ id: c.resource_id, name: `${resource.name} — ${c.sub_id || c.name}` }));
    return list;
  }, [resource]);

  useEffect(() => {
    // Iter 338 — sessionStorage-cached refdata (10 min TTL). Re-opening
    // the dialog now resolves in <5 ms vs. ~300 ms previously.
    if (resource.allow_catering) {
      fetchCateringItems().then(setAvailableItems).catch(() => {});
    }
    fetchCostCenters().then(setCostCenters).catch(() => {});
    fetchAccounts().then(setAccounts).catch(() => {});
    fetchBookableUsers().then(setBookableUsers).catch(() => setBookableUsers([]));
  }, [resource]);

  // Conflict check with free-slot suggestions on conflict
  useEffect(() => {
    if (!target || !start || !end) return;
    // Iter 338 — validate inside the debounce, NOT immediately, so the user
    // can type a new end-time (e.g. "12" before adding ":00") without the
    // "Endzeit muss nach Startzeit liegen" error firing on every keystroke.
    setChecking(true);
    const handle = setTimeout(async () => {
      if (new Date(end) <= new Date(start)) {
        setConflicts([{ reason: 'invalid_window', title: 'Endzeit muss nach Startzeit liegen' }]);
        setSuggestions([]);
        setChecking(false);
        return;
      }
      try {
        const { data } = await api.post(`/resources/${target}/check-conflicts`, {
          start_at: new Date(start).toISOString(),
          end_at: new Date(end).toISOString(),
        });
        const c = data.conflicts || [];
        setConflicts(c);
        if (c.length) {
          try {
            const dur = Math.round((new Date(end) - new Date(start)) / 60000);
            const { data: s } = await api.post(`/resources/${target}/suggest-slots`, {
              start_at: new Date(start).toISOString(),
              duration_min: dur,
              count: 3,
            });
            setSuggestions(s.suggestions || []);
          } catch { setSuggestions([]); }
        } else {
          setSuggestions([]);
        }
      } catch {
        setConflicts([]);
        setSuggestions([]);
      } finally {
        setChecking(false);
      }
    }, 700);
    return () => clearTimeout(handle);
  }, [target, start, end]);

  // Iter 339 — Issue #3: parallel availability check for ALL targets (parent
  // + every sub-room) so the dropdown can show "frei" / "belegt 09:00–10:00".
  // Runs only when the resource is splittable (multiple targets exist).
  useEffect(() => {
    if (!start || !end || targets.length <= 1) {
      setTargetAvailability({});
      return;
    }
    if (new Date(end) <= new Date(start)) return;
    let cancelled = false;
    const handle = setTimeout(async () => {
      const result = {};
      await Promise.all(targets.map(async (t) => {
        try {
          const { data } = await api.post(`/resources/${t.id}/check-conflicts`, {
            start_at: new Date(start).toISOString(),
            end_at: new Date(end).toISOString(),
          });
          const c = data?.conflicts || [];
          result[t.id] = c.length ? { state: 'busy', conflicts: c } : { state: 'free', conflicts: [] };
        } catch {
          result[t.id] = { state: 'unknown', conflicts: [] };
        }
      }));
      if (!cancelled) setTargetAvailability(result);
    }, 750);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [start, end, targets]);

  const setDuration = (minutes) => {
    const startDate = new Date(start);
    if (isNaN(startDate.getTime())) return;
    const newEnd = new Date(startDate.getTime() + minutes * 60000);
    setEnd(toLocal(newEnd));
  };

  // Iter 343 — Single source of truth: target is derived from comboSubs.
  //   0 selected → book parent (whole room)
  //   1 selected → book that single sub-room
  //   >=2       → kombi-booking (submit path handles)
  // Backwards-compat: non-splittable resources still use setTarget directly.
  useEffect(() => {
    if (!resource.is_splitable) return;
    if (comboSubs.length === 1) {
      const sub = (resource.children || []).find(c => c.sub_id === comboSubs[0]);
      if (sub?.resource_id && sub.resource_id !== target) setTarget(sub.resource_id);
    } else if (comboSubs.length === 0) {
      if (target !== resource.resource_id) setTarget(resource.resource_id);
    }
    // For length >=2 we keep `target` as-is — submit() detects combo via
    // comboSubs.length and posts to /resource-bookings/combo regardless.
  }, [comboSubs, resource]);  // eslint-disable-line react-hooks/exhaustive-deps

  const setQuickDate = (mode) => {
    const d = new Date();
    d.setMinutes(0, 0, 0);
    if (mode === 'today-now') {
      d.setHours(d.getHours() + 1);
    } else if (mode === 'today-afternoon') {
      d.setHours(14);
    } else if (mode === 'tomorrow-am') {
      d.setDate(d.getDate() + 1);
      d.setHours(9);
    } else if (mode === 'tomorrow-pm') {
      d.setDate(d.getDate() + 1);
      d.setHours(14);
    } else if (mode === 'next-week') {
      d.setDate(d.getDate() + 7);
      d.setHours(9);
    }
    const endD = new Date(d.getTime() + 60 * 60000);
    setStart(toLocal(d));
    setEnd(toLocal(endD));
  };

  const acceptSuggestion = (s) => {
    setStart(toLocal(new Date(s.start_at)));
    setEnd(toLocal(new Date(s.end_at)));
    toast.success('Slot übernommen');
  };

  const addCateringLine = () => {
    if (!availableItems.length) return;
    setCateringItems(prev => [...prev, { item_id: availableItems[0].item_id, quantity: 1 }]);
  };
  const updateLine = (idx, patch) => {
    setCateringItems(prev => prev.map((l, i) => i === idx ? { ...l, ...patch } : l));
  };
  const removeLine = (idx) => setCateringItems(prev => prev.filter((_, i) => i !== idx));

  const cateringTotal = useMemo(() => {
    const idx = Object.fromEntries(availableItems.map(it => [it.item_id, it]));
    return cateringItems.reduce((sum, ln) => {
      const it = idx[ln.item_id];
      return sum + (it ? (it.price || 0) * (ln.quantity || 0) : 0);
    }, 0);
  }, [cateringItems, availableItems]);
  const totalQty = cateringItems.reduce((s, ln) => s + (Number(ln.quantity) || 0), 0);

  // Iter 322 (Thema 2) — Lead-time validation: every catering item has a
  // `lead_time_min` (default 60 min). The kitchen team needs that many
  // minutes between "now" and the meeting start to prepare. If the user
  // tries to book within that window, show a warning (soft — kitchen may
  // still accept). The strictest item (max lead_time) drives the warning.
  const leadTimeWarning = useMemo(() => {
    if (!cateringEnabled || !cateringItems.length || !start) return null;
    const idx = Object.fromEntries(availableItems.map(it => [it.item_id, it]));
    let maxLead = 0;
    let worstName = null;
    for (const ln of cateringItems) {
      const it = idx[ln.item_id];
      const lt = Number(it?.lead_time_min ?? 60);
      if (lt > maxLead) { maxLead = lt; worstName = it?.name || 'Artikel'; }
    }
    const startMs = new Date(start).getTime();
    if (!Number.isFinite(startMs)) return null;
    const minsUntil = Math.round((startMs - Date.now()) / 60000);
    if (minsUntil < maxLead) {
      return {
        max_lead_min: maxLead,
        mins_until_start: minsUntil,
        worst_item: worstName,
        // human-readable "X Std. Y Min."
        max_lead_human: maxLead >= 60
          ? `${Math.floor(maxLead / 60)} Std. ${maxLead % 60 ? `${maxLead % 60} Min.` : ''}`.trim()
          : `${maxLead} Min.`,
      };
    }
    return null;
  }, [cateringEnabled, cateringItems, availableItems, start]);

  // Iter 338 — submit accepts an opts.allowPendingOverlap flag. When true,
  // the backend (`/resource-bookings`) ignores `pending_approval` conflicts
  // and accepts the booking as a parallel pending request. Hard `confirmed`
  // conflicts still 409.
  const submit = async (opts = {}) => {
    const allowPendingOverlap = !!opts.allowPendingOverlap;
    // The hard "conflicts.length" gate is bypassed when the user explicitly
    // opted to override pending-conflicts (the panel button).
    const hardConflict = !allowPendingOverlap && conflicts.length > 0;
    if (hardConflict || !title || !start || !end) return;
    setSubmitting(true);
    if (seriesEnabled) {
      try {
        const r = await api.post('/resource-bookings/series', {
          resource_id: target,
          title,
          start_at: new Date(start).toISOString(),
          end_at: new Date(end).toISOString(),
          recurrence: seriesRecurrence,
          // Iter 334 — Pro Custom-Daten oder occurrence-Anzahl
          ...(seriesRecurrence === 'custom'
            ? { custom_dates: seriesCustomDates }
            : { occurrences: Math.max(1, Math.min(52, Number(seriesOccurrences) || 4)) }),
          purpose: purpose || undefined,
          cost_center: costCenter || undefined,
          account: account || undefined,
        });
        const data = r.data;
        const ok = data.created?.length || 0;
        const skipped = data.skipped?.length || 0;
        if (ok > 0) {
          toast.success(`${ok} Serie-Termin(e) angelegt${skipped ? `, ${skipped} wegen Konflikt übersprungen` : ''}`);
          onClose(true);
        } else {
          toast.error('Alle Termine wegen Konflikt übersprungen — Zeit anpassen');
        }
        return;
      } catch (e) {
        toast.error(e.response?.data?.detail || 'Serie konnte nicht angelegt werden');
        return;
      } finally {
        setSubmitting(false);
      }
    }
    if (comboSubs.length >= 2 && resource.is_splitable) {
      try {
        await api.post('/resource-bookings/combo', {
          parent_resource_id: resource.resource_id,
          sub_ids: comboSubs,
          title,
          start_at: new Date(start).toISOString(),
          end_at: new Date(end).toISOString(),
          cost_center: costCenter || undefined,
          account: account || undefined,
        });
        toast.success(`Kombi-Buchung ${comboSubs.join('+')} angelegt`);
        onClose(true);
        return;
      } catch (e) {
        toast.error(e.response?.data?.detail || 'Kombi-Buchung fehlgeschlagen');
        return;
      } finally {
        setSubmitting(false);
      }
    }
    const body = {
      resource_id: target,
      title,
      start_at: new Date(start).toISOString(),
      end_at: new Date(end).toISOString(),
      purpose: purpose || undefined,
      destination: destination || undefined,
      mileage_before: mileageBefore ? Number(mileageBefore) : undefined,
      cost_center: costCenter || undefined,
      account: account || undefined,
      booked_for_user_id: bookedForUserId || undefined,
      // Iter 338 — Issue 3
      allow_pending_overlap: allowPendingOverlap || undefined,
    };
    if (cateringEnabled && cateringItems.length) {
      body.catering = {
        items: cateringItems,
        attachments: cateringAttachments.map(a => a.attachment_id || a.id || a),
      };
    }
    try {
      await api.post('/resource-bookings', body);
      toast.success('Buchung angelegt');
      onClose(true);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409) {
        const c = typeof detail === 'object' ? detail?.conflicts : null;
        setConflicts(c || []);
        toast.error('Konflikt: Zeitraum bereits belegt');
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Buchung fehlgeschlagen');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const targetRes = target === resource.resource_id ? resource :
    (resource.children || []).find(c => c.resource_id === target);
  const allowCatering = (targetRes?.allow_catering) ?? resource.allow_catering;

  // Iter 338 — pending-approval conflicts are surfaced via the conflict
  // panel's "Trotzdem buchen" override button, so the regular Submit button
  // stays disabled to keep the two flows visually distinct.
  const disabledReason = !title ? 'Titel fehlt' :
    !start || !end ? 'Zeitraum fehlt' :
    new Date(end) <= new Date(start) ? 'Endzeit muss nach Startzeit liegen' :
    conflicts.length ? 'Zeitfenster belegt — Vorschlag wählen oder Zeit anpassen' :
    null;

  const durationMin = Math.max(0, Math.round((new Date(end) - new Date(start)) / 60000));

  return {
    // values
    target, title, start, end, purpose, destination, mileageBefore, costCenter, account,
    cateringEnabled, cateringItems, cateringAttachments, availableItems, costCenters, accounts,
    comboSubs, conflicts, suggestions, checking, submitting, showAdvanced,
    seriesEnabled, seriesRecurrence, seriesOccurrences, seriesCustomDates, bookableUsers, bookedForUserId,
    // Iter 339 — Issue #3
    targetAvailability,
    // derived
    targets, cateringTotal, totalQty, allowCatering, disabledReason, durationMin,
    leadTimeWarning,
    // setters
    setTarget, setTitle, setStart, setEnd, setPurpose, setDestination, setMileageBefore,
    setCostCenter, setAccount, setCateringEnabled, setCateringAttachments, setComboSubs,
    setShowAdvanced, setSeriesEnabled, setSeriesRecurrence, setSeriesOccurrences, setSeriesCustomDates, setBookedForUserId,
    // actions
    setDuration, setQuickDate, acceptSuggestion, addCateringLine, updateLine, removeLine, submit,
  };
}
