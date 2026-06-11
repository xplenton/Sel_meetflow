import { useState, useMemo } from 'react';
import api from '../../lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { Switch } from '../ui/switch';
import { Label } from '../ui/label';
import { Upload, AlertTriangle, CheckCircle2, Download, FileText } from 'lucide-react';
import { toast } from 'sonner';

/**
 * BulkUserImportDialog (iter 341) — CSV bulk import for users with the
 * extended master-data model.
 *
 * Flow:
 *   1. User pastes CSV text OR uploads .csv file.
 *   2. Preview parses header + first rows into a table; invalid rows are
 *      tagged in red.
 *   3. Click "Importieren" → POST /admin/users/bulk-import.
 *   4. Result panel shows per-row outcome + summary counters.
 *
 * CSV columns (header row, case-insensitive):
 *   email,first_name,last_name,display_name,phone,department,role,group_ids
 *
 * `group_ids` accepts either group_id values or human-readable group names
 * (the backend resolves names against the groups collection), separated
 * by `;` or `,`.
 */
const EXPECTED_COLS = [
  'email', 'first_name', 'last_name', 'display_name',
  'phone', 'department', 'role', 'group_ids',
];

function parseCsv(text) {
  // RFC-light CSV: handles quoted values + escaped quotes ("") + comma/semicolon
  // separators. The header row is required.
  const lines = text.replace(/\r\n?/g, '\n').split('\n').filter(l => l.trim().length > 0);
  if (!lines.length) return { header: [], rows: [], delim: ',' };
  // Auto-detect delimiter: pick the one with more occurrences on the header line
  const delim = (lines[0].split(';').length > lines[0].split(',').length) ? ';' : ',';
  const parseLine = (line) => {
    const out = [];
    let cur = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"') {
          if (line[i + 1] === '"') { cur += '"'; i++; }
          else inQuotes = false;
        } else cur += ch;
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === delim) {
        out.push(cur); cur = '';
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out;
  };
  const header = parseLine(lines[0]).map(h => h.trim().toLowerCase().replace(/[^a-z0-9_]/g, ''));
  const rows = lines.slice(1).map(parseLine);
  return { header, rows, delim };
}

export default function BulkUserImportDialog({ open, onOpenChange, onImported }) {
  const [csvText, setCsvText] = useState('');
  const [sendEmail, setSendEmail] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const parsed = useMemo(() => parseCsv(csvText), [csvText]);

  // Map parsed rows → {email, first_name, ...} objects for the API.
  const preparedRows = useMemo(() => {
    if (!parsed.header.length) return [];
    return parsed.rows.map(cells => {
      const obj = {};
      parsed.header.forEach((col, i) => {
        if (EXPECTED_COLS.includes(col)) obj[col] = (cells[i] || '').trim();
      });
      return obj;
    });
  }, [parsed]);

  const headerErrors = useMemo(() => {
    if (!parsed.header.length) return [];
    if (!parsed.header.includes('email')) return ['Spalte "email" fehlt — sie ist Pflicht'];
    const unknown = parsed.header.filter(h => h && !EXPECTED_COLS.includes(h));
    return unknown.length ? [`Unbekannte Spalten (werden ignoriert): ${unknown.join(', ')}`] : [];
  }, [parsed]);

  const validRowCount = preparedRows.filter(r => r.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.email)).length;

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv') && file.type !== 'text/csv') {
      toast.error('Nur .csv-Dateien erlaubt');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Datei zu groß (max. 2 MB)');
      return;
    }
    const text = await file.text();
    setCsvText(text);
  };

  const downloadTemplate = () => {
    const csv = [
      EXPECTED_COLS.join(','),
      'max.mustermann@firma.de,Max,Mustermann,Max M.,+49 30 1234567,Marketing,member,Analytics;Marketing-Team',
      'erika.musterfrau@firma.de,Erika,Musterfrau,,+49 30 9876543,IT,admin,IT-Admins',
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'meetflow-users-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async () => {
    if (!preparedRows.length || headerErrors.length) return;
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post('/admin/users/bulk-import', {
        rows: preparedRows,
        send_email: sendEmail,
      });
      setResult(data);
      const created = data?.summary?.created || 0;
      if (created > 0) toast.success(`${created} Nutzer angelegt`);
      else toast.message('Keine neuen Nutzer angelegt');
      if (created > 0 && onImported) onImported();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Import fehlgeschlagen');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setCsvText(''); setResult(null); };

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="sm:max-w-[720px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>CSV-Bulk-Import</DialogTitle>
        </DialogHeader>
        {!result ? (
          <div className="space-y-3 pt-2">
            <p className="text-xs text-[#6B7280]">
              Spalten: <code className="bg-[#F3F4F1] px-1 py-0.5 rounded">{EXPECTED_COLS.join(', ')}</code>.
              Pflichtspalte: <strong>email</strong>. <strong>group_ids</strong> akzeptiert Gruppen-IDs oder -Namen, getrennt mit „;" oder „,".
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={downloadTemplate} className="rounded-xl text-xs" data-testid="bulk-download-template">
                <Download className="w-3.5 h-3.5 mr-1" /> Vorlage herunterladen
              </Button>
              <label className="inline-flex items-center gap-1 cursor-pointer">
                <Button asChild variant="outline" size="sm" className="rounded-xl text-xs" data-testid="bulk-upload-csv">
                  <span><Upload className="w-3.5 h-3.5 mr-1" /> CSV-Datei auswählen</span>
                </Button>
                <input type="file" accept=".csv,text/csv" onChange={handleFile} className="hidden" />
              </label>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">CSV-Daten</Label>
              <Textarea
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                placeholder={`${EXPECTED_COLS.join(',')}\nmax@firma.de,Max,Mustermann,,+49 ...,Marketing,member,Analytics`}
                className="font-mono text-[11px] min-h-[140px] border-[#E2E4E0]"
                data-testid="bulk-csv-textarea"
              />
            </div>

            {headerErrors.length > 0 && (
              <div className="rounded-lg border border-rose-300 bg-rose-50 p-2.5 text-xs text-rose-800 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <div>
                  {headerErrors.map((e, i) => <div key={i}>{e}</div>)}
                </div>
              </div>
            )}

            {preparedRows.length > 0 && (
              <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
                <div className="bg-[#F3F4F1] px-3 py-1.5 text-[11px] font-medium text-[#4A5D4E] flex items-center justify-between">
                  <span>Vorschau ({preparedRows.length} Zeilen, {validRowCount} gültig)</span>
                  <FileText className="w-3 h-3" />
                </div>
                <div className="max-h-[200px] overflow-y-auto">
                  <table className="w-full text-[11px]" data-testid="bulk-preview-table">
                    <thead className="bg-white sticky top-0 border-b border-[#E2E4E0]">
                      <tr className="text-left text-[#6B7280]">
                        <th className="px-2 py-1">E-Mail</th>
                        <th className="px-2 py-1">Name</th>
                        <th className="px-2 py-1">Rolle</th>
                        <th className="px-2 py-1">Abteilung</th>
                        <th className="px-2 py-1">Gruppen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preparedRows.slice(0, 20).map((r, i) => {
                        const emailValid = r.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.email);
                        return (
                          <tr key={i} className={emailValid ? '' : 'bg-rose-50'} data-testid={`bulk-preview-row-${i}`}>
                            <td className="px-2 py-1 font-mono text-[10px]">{r.email || <em className="text-rose-600">fehlt</em>}</td>
                            <td className="px-2 py-1">{[r.first_name, r.last_name].filter(Boolean).join(' ') || r.display_name || '—'}</td>
                            <td className="px-2 py-1">{r.role || 'member'}</td>
                            <td className="px-2 py-1">{r.department || '—'}</td>
                            <td className="px-2 py-1 text-[10px] text-[#6B7280]">{r.group_ids || '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {preparedRows.length > 20 && (
                    <div className="px-2 py-1.5 text-[10px] text-[#9CA3AF] text-center">
                      … und {preparedRows.length - 20} weitere
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between bg-[#F3F4F1] rounded-lg p-2.5">
              <Label className="text-xs flex items-center gap-2">
                <span>Einladungs-Mail versenden</span>
              </Label>
              <Switch checked={sendEmail} onCheckedChange={setSendEmail} data-testid="bulk-send-email-toggle" />
            </div>
          </div>
        ) : (
          <div className="space-y-3 pt-2">
            <div className="grid grid-cols-4 gap-2">
              <SummaryCard label="Angelegt" value={result.summary?.created || 0} color="text-emerald-700" />
              <SummaryCard label="Existieren" value={result.summary?.skipped_existing || 0} color="text-amber-700" />
              <SummaryCard label="Ungültig" value={result.summary?.invalid_email || 0} color="text-rose-700" />
              <SummaryCard label="Mails OK" value={result.summary?.mails_sent || 0} color="text-blue-700" />
            </div>
            <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
              <div className="max-h-[300px] overflow-y-auto">
                <table className="w-full text-[11px]" data-testid="bulk-result-table">
                  <thead className="bg-[#F3F4F1] sticky top-0 border-b border-[#E2E4E0]">
                    <tr className="text-left text-[#6B7280]">
                      <th className="px-2 py-1">Status</th>
                      <th className="px-2 py-1">E-Mail</th>
                      <th className="px-2 py-1">Passwort</th>
                      <th className="px-2 py-1">Mail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.results || []).map((r, i) => (
                      <tr key={i} className={r.status === 'created' ? '' : (r.status === 'skipped_existing' ? 'bg-amber-50' : 'bg-rose-50')}>
                        <td className="px-2 py-1">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="px-2 py-1 font-mono text-[10px]">{r.email || '—'}</td>
                        <td className="px-2 py-1 font-mono text-[10px]">{r.temp_password || '—'}</td>
                        <td className="px-2 py-1">
                          {r.email_sent ? <CheckCircle2 className="w-3 h-3 text-emerald-600 inline" />
                            : r.email_simulated ? <span className="text-amber-700 text-[10px]">simuliert</span>
                            : r.email_error ? <span className="text-rose-700 text-[10px]" title={r.email_error}>Fehler</span>
                            : <span className="text-[#9CA3AF]">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
        <DialogFooter>
          {result ? (
            <>
              <Button variant="outline" onClick={reset} className="rounded-full border-[#E2E4E0]">Neu beginnen</Button>
              <Button onClick={() => onOpenChange(false)} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full">Schließen</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy} className="rounded-full border-[#E2E4E0]">Abbrechen</Button>
              <Button
                onClick={handleImport}
                disabled={busy || !validRowCount || headerErrors.length > 0}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
                data-testid="bulk-import-submit"
              >
                {busy ? 'Importiere…' : `${validRowCount} Nutzer importieren`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryCard({ label, value, color }) {
  return (
    <div className="bg-[#F3F4F1] rounded-lg p-2 text-center">
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-[#6B7280]">{label}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    created: { txt: 'Angelegt', cls: 'bg-emerald-100 text-emerald-800' },
    skipped_existing: { txt: 'Existiert', cls: 'bg-amber-100 text-amber-800' },
    skipped_duplicate: { txt: 'Duplikat', cls: 'bg-amber-100 text-amber-800' },
    invalid_email: { txt: 'Ungültig', cls: 'bg-rose-100 text-rose-800' },
    error: { txt: 'Fehler', cls: 'bg-rose-100 text-rose-800' },
  };
  const s = map[status] || { txt: status, cls: 'bg-gray-100 text-gray-800' };
  return <Badge variant="outline" className={`text-[9px] ${s.cls}`}>{s.txt}</Badge>;
}
