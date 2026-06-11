import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Badge } from './ui/badge';
import { ScrollText, RefreshCw } from 'lucide-react';
import api from '../lib/api';

import { useLanguage } from '../contexts/LanguageContext';
function formatTs(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

const ACTION_CFG = {
  created: { label: 'Erstellt', color: '#6B8E23' },
  updated: { label: 'Geaendert', color: '#D4A373' },
  published: { label: 'Veroeffentlicht', color: '#4A5D4E' },
  deleted: { label: 'Gelöscht', color: '#C87967' },
  approved_and_published: { label: 'Freigegeben', color: '#6B8E23' },
  submitted_review: { label: 'Zur Prüfung', color: '#D4A373' },
  rejected: { label: 'Abgelehnt', color: '#C87967' },
};

export default function AuditLogPanel() {
  const { t } = useLanguage();
  const [actionFilter, setActionFilter] = useState('all');

  // React Query (iter 118): key includes the action filter so changing it
  // triggers an automatic refetch. The shared `ws:reconnected` listener in
  // `lib/queryClient.js` also invalidates this view whenever a silent WS
  // drop is healed, so the audit trail stays live.
  const auditQ = useQuery({
    queryKey: ['admin', 'audit-log', actionFilter],
    queryFn: async () => {
      const params = actionFilter === 'all' ? {} : { action: actionFilter };
      const { data } = await api.get('/news/audit', { params: { limit: 200, ...params } });
      return data || [];
    },
  });
  const entries = auditQ.data || [];
  const loading = auditQ.isLoading;

  return (
    <div data-testid="audit-log-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Select value={actionFilter} onValueChange={setActionFilter}>
            <SelectTrigger className="w-[200px] h-8 text-xs rounded-lg border-[#E2E4E0]" data-testid="audit-action-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('allActions')}</SelectItem>
              <SelectItem value="created">Erstellt</SelectItem>
              <SelectItem value="updated">Geaendert</SelectItem>
              <SelectItem value="published">Veroeffentlicht</SelectItem>
              <SelectItem value="deleted">Gelöscht</SelectItem>
              <SelectItem value="approved_and_published">Freigegeben</SelectItem>
              <SelectItem value="rejected">Abgelehnt</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={() => auditQ.refetch()} className="rounded-full text-xs h-8 border-[#E2E4E0]"
          data-testid="audit-refresh">
          <RefreshCw className="w-3 h-3 mr-1" />Aktualisieren
        </Button>
      </div>
      {loading ? (
        <div className="text-center py-12 text-[#9CA3AF] text-sm">Laden...</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
          <ScrollText className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
          <p className="text-sm text-[#9CA3AF]">{t('noEntries')}</p>
        </div>
      ) : (
        <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#F3F4F1]">
              <tr>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Zeit</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Aktion</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Nutzer</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Details</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Post-ID</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
                const cfg = ACTION_CFG[e.action] || { label: e.action, color: '#9CA3AF' };
                return (
                  <tr key={i} className={i % 2 ? 'bg-[#F9F9F8]' : 'bg-white'} data-testid={`audit-row-${i}`}>
                    <td className="px-4 py-2 text-xs text-[#9CA3AF] whitespace-nowrap">{formatTs(e.timestamp)}</td>
                    <td className="px-4 py-2">
                      <Badge className="text-[10px] border-0" style={{ backgroundColor: `${cfg.color}18`, color: cfg.color }}>{cfg.label}</Badge>
                    </td>
                    <td className="px-4 py-2 text-xs text-[#1C1F1D]">{e.user_name || e.user_id || '-'}</td>
                    <td className="px-4 py-2 text-xs text-[#6B7280] max-w-[300px] truncate" title={e.details}>{e.details || '-'}</td>
                    <td className="px-4 py-2 text-[10px] text-[#9CA3AF] font-mono">{e.post_id}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
