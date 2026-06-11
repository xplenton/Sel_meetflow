import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Card } from '../ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

/** Per-resource blackout / maintenance editor (admin). */
export default function BlackoutEditorDialog({ resource, onClose }) {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ start_at: '', end_at: '', title: 'Sperrzeit', reason: 'maintenance' });

  const load = () => api.get(`/resources/${resource.resource_id}/blackouts`)
    .then(r => setItems(r.data || [])).catch(() => setItems([]));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [resource.resource_id]);

  const add = async () => {
    if (!form.start_at || !form.end_at) { toast.error('Zeitraum fehlt'); return; }
    try {
      await api.post(`/resources/${resource.resource_id}/blackouts`, {
        start_at: new Date(form.start_at).toISOString(),
        end_at: new Date(form.end_at).toISOString(),
        title: form.title, reason: form.reason,
      });
      setForm({ start_at: '', end_at: '', title: 'Sperrzeit', reason: 'maintenance' });
      load();
      toast.success('Sperrzeit angelegt');
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };
  const remove = async (id) => {
    try { await api.delete(`/resources/blackouts/${id}`); load(); } catch { /* ignore */ }
  };

  return (
    <Dialog open onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-xl w-[calc(100vw-1.5rem)] max-h-[90vh] overflow-y-auto" data-testid="blackout-editor">
        <DialogHeader>
          <DialogTitle>Sperrzeiten — {resource.name}</DialogTitle>
        </DialogHeader>

        <div className="space-y-2">
          {items.length === 0 && <div className="text-xs text-[#9CA3AF]">Keine Sperrzeiten.</div>}
          {items.map(b => (
            <Card key={b.blackout_id} className="p-2 flex items-center justify-between" data-testid={`blackout-row-${b.blackout_id}`}>
              <div>
                <div className="text-sm font-medium">{b.title}</div>
                <div className="text-xs text-[#6B7280]">
                  {new Date(b.start_at).toLocaleString('de-DE')} – {new Date(b.end_at).toLocaleString('de-DE')}
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => remove(b.blackout_id)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            </Card>
          ))}
        </div>

        <div className="border-t border-[#E2E4E0] pt-3 mt-3">
          <Label className="text-xs">Neue Sperrzeit</Label>
          <div className="grid grid-cols-2 gap-2 mt-1">
            <Input type="datetime-local" value={form.start_at}
              onChange={e => setForm({ ...form, start_at: e.target.value })}
              data-testid="blackout-start" />
            <Input type="datetime-local" value={form.end_at}
              onChange={e => setForm({ ...form, end_at: e.target.value })}
              data-testid="blackout-end" />
            <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder="Titel" data-testid="blackout-title" />
            <Input value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })}
              placeholder="Grund (maintenance, vacation, ...)" />
          </div>
          <Button className="mt-2" size="sm" onClick={add} data-testid="blackout-add">
            <Plus className="w-4 h-4 mr-1" /> Hinzufügen
          </Button>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onClose(false)}>Schließen</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
