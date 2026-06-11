import { useState, useEffect, useCallback } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  FileSearch, RefreshCw, LogOut, Bell, KeyRound, Loader2, Globe,
  Search, Download, ChevronDown, ChevronUp, ClipboardCheck, Settings as SettingsIcon,
} from 'lucide-react';
import api from '../../lib/api';

import { useLanguage } from '../../contexts/LanguageContext';
function formatTs(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

const CATEGORY = {
  capabilities: { label: 'Rechte', icon: KeyRound, color: 'text-[#4A5D4E] bg-[#4A5D4E]/10' },
  session: { label: 'Session', icon: LogOut, color: 'text-[#C87967] bg-[#C87967]/10' },
  alert: { label: 'Alert', icon: Bell, color: 'text-[#D4A373] bg-[#D4A373]/10' },
  bookings: { label: 'Buchungen', icon: ClipboardCheck, color: 'text-blue-700 bg-blue-50' },
};

// Iter 267 — Erweiterte Action-Labels (alle bekannten Actions aus DB)
const ACTION_LABELS = {
  // Capabilities
  set_caps: 'Rechte geändert',
  apply_preset: 'Preset angewandt',
  auto_assign: 'Auto-Regel',
  bulk_apply: 'Bulk-Preset',
  create_preset: 'Preset erstellt', update_preset: 'Preset geändert', delete_preset: 'Preset gelöscht',
  create_rule: 'Regel erstellt', update_rule: 'Regel geändert', delete_rule: 'Regel gelöscht',
  // Session
  force_logout: 'Session beendet',
  force_logout_all: 'Alle Sessions beendet',
  // Alerts
  health_alert: 'Health-Alert gesendet',
  // Bookings
  booking_created: 'Buchung erstellt',
  booking_updated: 'Buchung geändert',
  booking_cancelled: 'Buchung storniert',
  combo_booking_created: 'Combo-Buchung erstellt',
  checked_in: 'Check-In',
  checked_out: 'Check-Out',
  damage_reported: 'Schadensmeldung',
  attachment_added: 'Anhang hinzugefügt',
  attachment_removed: 'Anhang entfernt',
  invoice_approve: 'Rechnung freigegeben',
  office_day_autogen: 'Bürotag automatisch',
  office_day_skipped: 'Bürotag übersprungen',
  office_day_skip_deleted: 'Bürotag gelöscht',
};

const TIME_RANGES = [
  { value: '0', label: 'Alle' },
  { value: '1', label: 'Letzte Stunde' },
  { value: '24', label: 'Letzte 24h' },
  { value: '168', label: 'Letzte 7 Tage' },
  { value: '720', label: 'Letzte 30 Tage' },
];

export default function SystemAuditPanel() {
  const { t } = useLanguage();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('all');
  const [action, setAction] = useState('all');
  const [actor, setActor] = useState('');
  const [search, setSearch] = useState('');
  const [sinceHours, setSinceHours] = useState('0');
  const [skip, setSkip] = useState(0);
  const [expanded, setExpanded] = useState(new Set()); // audit_ids whose JSON is expanded
  const limit = 100;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit, skip };
      if (category !== 'all') params.category = category;
      if (action !== 'all') params.action = action;
      if (actor.trim()) params.actor = actor.trim();
      if (search.trim()) params.search = search.trim();
      if (sinceHours !== '0') params.since_hours = sinceHours;
      const { data } = await api.get('/admin/audit/system', { params });
      setEntries(data.entries || []);
      setTotal(data.total || 0);
    } catch { setEntries([]); }
    finally { setLoading(false); }
  }, [category, action, actor, search, sinceHours, skip]);

  // Re-fetch when filters change (debounced for text inputs)
  useEffect(() => {
    const tm = setTimeout(fetchData, 250);
    return () => clearTimeout(tm);
  }, [fetchData]);

  // Reset skip when filters change (not when skip itself changes)
  useEffect(() => { setSkip(0); }, [category, action, actor, search, sinceHours]);

  const handleCsvExport = () => {
    const apiBase = process.env.REACT_APP_BACKEND_URL || '';
    const params = new URLSearchParams();
    if (category !== 'all') params.set('category', category);
    if (action !== 'all') params.set('action', action);
    if (actor.trim()) params.set('actor', actor.trim());
    if (sinceHours !== '0') params.set('since_hours', sinceHours);
    window.open(`${apiBase}/api/admin/audit/system.csv?${params.toString()}`, '_blank');
  };

  const toggleExpand = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div data-testid="system-audit-panel" className="space-y-4">
      {/* Filter Row 1: Kategorie + Aktion + Zeit + Refresh + CSV-Export */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="w-[150px] h-8 text-xs rounded-lg border-[#E2E4E0]" data-testid="audit-category-filter">
              <SelectValue placeholder="Kategorie" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('allCategories') || 'Alle Kategorien'}</SelectItem>
              <SelectItem value="capabilities">{t('permissionChanges') || 'Rechte'}</SelectItem>
              <SelectItem value="session">Session</SelectItem>
              <SelectItem value="alert">Alerts</SelectItem>
              <SelectItem value="bookings">Buchungen</SelectItem>
            </SelectContent>
          </Select>
          <Select value={action} onValueChange={setAction}>
            <SelectTrigger className="w-[170px] h-8 text-xs rounded-lg border-[#E2E4E0]" data-testid="audit-action-filter">
              <SelectValue placeholder="Aktion" />
            </SelectTrigger>
            <SelectContent className="max-h-80">
              <SelectItem value="all">{t('allActions') || 'Alle Aktionen'}</SelectItem>
              {Object.entries(ACTION_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={sinceHours} onValueChange={setSinceHours}>
            <SelectTrigger className="w-[140px] h-8 text-xs rounded-lg border-[#E2E4E0]" data-testid="audit-time-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_RANGES.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={fetchData} disabled={loading}
            className="h-8 text-xs rounded-full border-[#E2E4E0]" data-testid="audit-refresh-btn"
            title="Aktualisieren">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          </Button>
          <Button size="sm" variant="outline" onClick={handleCsvExport}
            className="h-8 text-xs rounded-full border-[#E2E4E0]" data-testid="audit-csv-export"
            title="CSV-Export aktueller Filter (max. 5000 Zeilen)">
            <Download className="w-3.5 h-3.5 mr-1" /> CSV
          </Button>
        </div>
        <span className="text-xs text-[#9CA3AF]" data-testid="audit-total-count">{total.toLocaleString('de-DE')} Einträge</span>
      </div>

      {/* Filter Row 2: Akteur + Such-Text */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
          <Input
            placeholder="Akteur (Name oder E-Mail)…"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            className="h-8 pl-7 text-xs"
            data-testid="audit-actor-filter"
          />
        </div>
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
          <Input
            placeholder="Suche in Action/Details…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-7 text-xs"
            data-testid="audit-search-input"
          />
        </div>
      </div>

      {loading && entries.length === 0 ? (
        <div className="py-12 text-center text-[#9CA3AF] flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Lade Audit-Log…
        </div>
      ) : entries.length === 0 ? (
        <div className="py-12 text-center text-[#9CA3AF] border border-dashed border-[#E2E4E0] rounded-xl" data-testid="audit-empty">
          <FileSearch className="w-8 h-8 mx-auto mb-2 opacity-40" />
          Keine Einträge gefunden{(actor || search || category !== 'all' || action !== 'all' || sinceHours !== '0') ? ' für diese Filter' : ''}.
        </div>
      ) : (
        <>
          <div className="space-y-1.5" data-testid="audit-list">
            {entries.map(e => {
              const catMeta = CATEGORY[e.category] || { label: e.category, icon: SettingsIcon, color: 'text-[#6B7280] bg-[#F3F4F1]' };
              const CatIcon = catMeta.icon;
              const isExpanded = expanded.has(e.audit_id);
              const hasDetails = e.details && Object.keys(e.details).length > 0;
              return (
                <div key={e.audit_id} className="border border-[#E2E4E0] rounded-lg p-3 hover:bg-[#F3F4F1]/50 transition-colors" data-testid={`audit-entry-${e.audit_id}`}>
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-start gap-2 min-w-0 flex-1">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-[0.1em] ${catMeta.color}`}>
                        <CatIcon className="w-3 h-3" /> {catMeta.label}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[#1C1F1D] truncate">
                          {ACTION_LABELS[e.action] || e.action}
                        </p>
                        <p className="text-[11px] text-[#6B7280] mt-0.5">
                          <strong>{e.actor_name || e.actor_id || 'system'}</strong>
                          {e.target_user_id && e.target_user_id !== 'admins' && e.target_user_id !== 'all_users' && (
                            <> → <span className="font-mono text-[10px]">{e.details?.target_email || e.target_user_id}</span></>
                          )}
                          {e.target_user_id === 'all_users' && <> → <em>{t('allUsers') || 'alle Nutzer'}</em></>}
                        </p>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-[11px] text-[#6B7280]">{formatTs(e.timestamp)}</p>
                      {e.ip && (
                        <p className="text-[10px] text-[#9CA3AF] font-mono flex items-center justify-end gap-1 mt-0.5" title={e.user_agent || ''}>
                          <Globe className="w-2.5 h-2.5" /> {e.ip}
                        </p>
                      )}
                    </div>
                  </div>
                  {/* Details summary (specific actions) */}
                  {hasDetails && (
                    <div className="mt-2 pt-2 border-t border-[#E2E4E0] text-[11px] text-[#6B7280] space-y-0.5">
                      {e.action === 'force_logout' && (
                        <p>Session invalidiert · neue token_version: <span className="font-mono">{e.details.new_token_version}</span></p>
                      )}
                      {e.action === 'force_logout_all' && (
                        <p>{e.details.modified_count} Nutzer abgemeldet</p>
                      )}
                      {e.action === 'health_alert' && (
                        <>
                          <p>{e.details.subject} · {e.details.severity}</p>
                          <p>{e.details.emails} E-Mail(s), {e.details.pushes} Push, {e.details.recipients} Empfänger</p>
                        </>
                      )}
                      {e.action === 'apply_preset' && (
                        <p>Preset: {e.details.preset_id || e.details.preset_name}</p>
                      )}
                      {e.action === 'auto_assign' && (
                        <p>Regel: {e.details.rule_name || e.details.rule_id} · {e.details.matched_count} Nutzer</p>
                      )}
                      {(e.action === 'booking_created' || e.action === 'booking_updated' || e.action === 'booking_cancelled') && (
                        <p>Buchung: <span className="font-mono">{e.details.booking_id || e.details.resource_id}</span></p>
                      )}
                      {/* JSON-Vollansicht — Toggle */}
                      <button
                        type="button"
                        onClick={() => toggleExpand(e.audit_id)}
                        className="mt-1 inline-flex items-center gap-1 text-[10px] text-[#4A5D4E] hover:underline"
                        data-testid={`audit-toggle-json-${e.audit_id}`}
                      >
                        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        {isExpanded ? 'Details verstecken' : 'Volldetails anzeigen'}
                      </button>
                      {isExpanded && (
                        <pre className="mt-1 bg-[#FAFBF9] border border-[#E2E4E0] rounded p-2 text-[10px] font-mono whitespace-pre-wrap break-all overflow-auto max-h-64" data-testid={`audit-json-${e.audit_id}`}>
                          {JSON.stringify(e.details, null, 2)}
                        </pre>
                      )}
                      {e.user_agent && (
                        <p className="truncate italic opacity-70" title={e.user_agent}>{e.user_agent}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 border-t border-[#E2E4E0]" data-testid="audit-pagination">
              <span className="text-[11px] text-[#9CA3AF]">
                Seite {currentPage} von {totalPages} · {entries.length} von {total} angezeigt
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm" variant="outline"
                  onClick={() => setSkip(Math.max(0, skip - limit))}
                  disabled={skip === 0 || loading}
                  className="h-7 text-[11px] rounded-full"
                  data-testid="audit-page-prev"
                >
                  ← Zurück
                </Button>
                <Button
                  size="sm" variant="outline"
                  onClick={() => setSkip(skip + limit)}
                  disabled={skip + limit >= total || loading}
                  className="h-7 text-[11px] rounded-full"
                  data-testid="audit-page-next"
                >
                  Weiter →
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
