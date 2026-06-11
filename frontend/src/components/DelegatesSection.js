import { useEffect, useState } from 'react';
import { Users, UserPlus, X, Loader2, Search } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import api from '../lib/api';
import { toast } from 'sonner';

/**
 * Iter 283 — Stellvertreter (Delegates) self-service.
 *
 * Lets the current user maintain a small list of colleagues who are
 * authorised to book resources on their behalf (room/desk/vehicle).
 * Search is debounced server-side via /api/users/search?q=...
 */
export default function DelegatesSection({ language = 'de' }) {
  const T = (de, en) => language === 'en' ? en : de;
  const [delegates, setDelegates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/users/me/delegates');
      setDelegates(data || []);
    } catch {
      setDelegates([]);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const h = setTimeout(async () => {
      setSearching(true);
      try {
        const { data } = await api.get('/users/search', { params: { q: query.trim(), limit: 10 } });
        setResults((data || []).filter(u => !delegates.find(d => d.user_id === u.user_id)));
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(h);
  }, [query, delegates]);

  const persist = async (newList) => {
    setSaving(true);
    try {
      const { data } = await api.put('/users/me/delegates', {
        user_ids: newList.map(u => u.user_id),
      });
      setDelegates(data || []);
      toast.success(T('Stellvertreter gespeichert', 'Delegates saved'));
    } catch (e) {
      toast.error(e.response?.data?.detail || T('Speichern fehlgeschlagen', 'Save failed'));
    } finally {
      setSaving(false);
    }
  };

  const addDelegate = (user) => {
    setQuery('');
    setResults([]);
    persist([...delegates, user]);
  };
  const removeDelegate = (uid) => {
    persist(delegates.filter(d => d.user_id !== uid));
  };

  return (
    <section className="bg-white border border-[#E2E4E0] rounded-2xl p-5" data-testid="delegates-section">
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-4 h-4 text-[#4A5D4E]" />
        <h3 className="text-[13px] font-bold text-[#1C1F1D]">
          {T('Stellvertreter (Buchungsvollmacht)', 'Delegates (booking authority)')}
        </h3>
        {(saving || loading) && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />}
      </div>
      <p className="text-[11px] text-[#6B7280] mb-3 leading-relaxed">
        {T(
          'Diese Personen dürfen Räume, Desks und Fahrzeuge in deinem Namen buchen. Sie sehen dich im "Buchen für"-Picker beim Anlegen einer Buchung.',
          'These people may book rooms, desks and vehicles on your behalf. They will see you in the "Book for" picker when creating a booking.',
        )}
      </p>

      {/* Current delegates */}
      {delegates.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4" data-testid="delegates-current-list">
          {delegates.map(d => (
            <div key={d.user_id}
                 className="inline-flex items-center gap-2 bg-[#F3F4F1] border border-[#E2E4E0] rounded-full pl-3 pr-1 py-1"
                 data-testid={`delegate-chip-${d.user_id}`}>
              <span className="text-xs font-medium text-[#1C1F1D]">{d.name || d.email}</span>
              <button
                type="button"
                className="w-5 h-5 rounded-full bg-white hover:bg-rose-50 text-[#9CA3AF] hover:text-rose-600 flex items-center justify-center transition-colors"
                onClick={() => removeDelegate(d.user_id)}
                disabled={saving}
                data-testid={`delegate-remove-${d.user_id}`}
                aria-label={T('Stellvertreter entfernen', 'Remove delegate')}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Search & add */}
      <div className="relative">
        <div className="flex items-center gap-2 border border-[#E2E4E0] rounded-lg px-3 py-1.5 focus-within:border-[#4A5D4E]">
          <Search className="w-4 h-4 text-[#9CA3AF]" />
          <Input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={T('Kolleg:in suchen (Name oder E-Mail)…', 'Search colleague (name or email)…')}
            className="border-0 shadow-none focus-visible:ring-0 px-0 py-0 h-auto text-sm"
            data-testid="delegate-search-input"
          />
          {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />}
        </div>
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-white border border-[#E2E4E0] rounded-lg shadow-lg max-h-60 overflow-y-auto"
               data-testid="delegate-search-results">
            {results.map(u => (
              <button
                key={u.user_id}
                type="button"
                onClick={() => addDelegate(u)}
                className="w-full text-left px-3 py-2 hover:bg-[#F3F4F1] flex items-center gap-2 border-b border-[#F3F4F1] last:border-0"
                data-testid={`delegate-result-${u.user_id}`}
              >
                <UserPlus className="w-3.5 h-3.5 text-[#4A5D4E]" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-[#1C1F1D] truncate">{u.name || '—'}</div>
                  <div className="text-[11px] text-[#9CA3AF] truncate">{u.email}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {delegates.length === 0 && !query && (
        <p className="text-[11px] text-[#9CA3AF] mt-3 italic">
          {T('Keine Stellvertreter hinterlegt.', 'No delegates configured.')}
        </p>
      )}
    </section>
  );
}
