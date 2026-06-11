import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Plus, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import CateringCancelConfigPanel from './CateringCancelConfigPanel';

/** Catering item CRUD panel (admin) — minimal inline editor.
 *  Iter 282 — Backend stores `lead_time_min` (Minutes) for backwards-
 *  compatibility, UI shows & edits in HOURS with 0.25h (15 min) granularity.
 *  Labels are now visible in the "Neu anlegen" form so admins immediately
 *  see what each field means.
 */
const minToH = (m) => (Number(m) || 0) / 60;
const hToMin = (h) => Math.round((Number(h) || 0) * 60);

export default function CateringItemsPanel({ canManage }) {
  const [items, setItems] = useState([]);
  const [newItem, setNewItem] = useState({ name: '', price: 0, unit: 'Stück', lead_time_h: 1 });

  const load = () => api.get('/catering-items').then(r => setItems(r.data || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!newItem.name.trim()) { toast.error('Name erforderlich'); return; }
    try {
      await api.post('/catering-items', {
        name: newItem.name,
        unit: newItem.unit,
        price: Number(newItem.price) || 0,
        lead_time_min: hToMin(newItem.lead_time_h),
      });
      setNewItem({ name: '', price: 0, unit: 'Stück', lead_time_h: 1 });
      load();
      toast.success('Artikel angelegt');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
  };
  const save = async (it) => {
    try {
      await api.put(`/catering-items/${it.item_id}`, {
        name: it.name, price: Number(it.price), unit: it.unit,
        lead_time_min: hToMin(it.lead_time_h),
      });
      toast.success('Gespeichert');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
  };
  const remove = async (it) => {
    if (!window.confirm(`"${it.name}" deaktivieren?`)) return;
    try {
      await api.delete(`/catering-items/${it.item_id}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
  };

  return (
    <div className="space-y-4" data-testid="catering-items-panel">
      {canManage && <CateringCancelConfigPanel />}
      {canManage && (
        <div className="border border-[#E2E4E0] rounded-lg p-4 bg-[#FAFBF9]">
          <div className="text-sm font-medium text-[#1C1F1D] mb-3">Neuen Artikel anlegen</div>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 items-end">
            <div>
              <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1">Name</Label>
              <Input placeholder="z. B. Kaffee" value={newItem.name}
                onChange={e => setNewItem({ ...newItem, name: e.target.value })}
                data-testid="catering-new-name" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1">Preis (EUR)</Label>
              <Input placeholder="z. B. 2.50" type="number" step="0.01" min="0"
                value={newItem.price}
                onChange={e => setNewItem({ ...newItem, price: e.target.value })}
                data-testid="catering-new-price" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1">Einheit</Label>
              <Input placeholder="z. B. Stück" value={newItem.unit}
                onChange={e => setNewItem({ ...newItem, unit: e.target.value })}
                data-testid="catering-new-unit" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1">Mindest-Vorlauf (Std.)</Label>
              <Input placeholder="z. B. 1" type="number" step="0.25" min="0"
                value={newItem.lead_time_h}
                onChange={e => setNewItem({ ...newItem, lead_time_h: e.target.value })}
                data-testid="catering-new-leadtime" />
            </div>
            <Button onClick={create} data-testid="catering-new-save" className="h-10">
              <Plus className="w-4 h-4 mr-1" />Anlegen
            </Button>
          </div>
          <p className="text-[11px] text-[#9CA3AF] mt-2">
            Tipp: Eingaben in <strong>Stunden</strong> (0,25 = 15 Min., 0,5 = 30 Min., 1 = 1 Std.). 0 bedeutet sofort verfügbar.
          </p>
        </div>
      )}

      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#F3F4F1] text-left text-xs text-[#6B7280]">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Preis (EUR)</th>
              <th className="px-3 py-2">Einheit</th>
              <th className="px-3 py-2">Mindest-Vorlauf (Std.)</th>
              {canManage && <th className="px-3 py-2">Aktion</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((it, idx) => (
              <tr key={it.item_id} className="border-t border-[#E2E4E0]" data-testid={`catering-item-row-${idx}`}>
                <td className="px-3 py-2">
                  {canManage ? (
                    <Input value={it.name} onChange={e => setItems(p => p.map(x => x.item_id === it.item_id ? { ...x, name: e.target.value } : x))} />
                  ) : it.name}
                </td>
                <td className="px-3 py-2">
                  {canManage ? (
                    <Input type="number" step="0.01" min="0" value={it.price}
                      onChange={e => setItems(p => p.map(x => x.item_id === it.item_id ? { ...x, price: e.target.value } : x))}
                      className="w-24" />
                  ) : `${Number(it.price).toFixed(2)} EUR`}
                </td>
                <td className="px-3 py-2">
                  {canManage ? (
                    <Input value={it.unit} onChange={e => setItems(p => p.map(x => x.item_id === it.item_id ? { ...x, unit: e.target.value } : x))} className="w-24" />
                  ) : it.unit}
                </td>
                <td className="px-3 py-2">
                  {canManage ? (
                    <Input type="number" step="0.25" min="0"
                      value={it.lead_time_h ?? minToH(it.lead_time_min)}
                      onChange={e => setItems(p => p.map(x => x.item_id === it.item_id ? { ...x, lead_time_h: e.target.value } : x))}
                      className="w-24" />
                  ) : `${minToH(it.lead_time_min).toFixed(2).replace(/\.?0+$/, '')} Std.`}
                </td>
                {canManage && (
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => save(it)} data-testid={`catering-save-${idx}`}><Save className="w-4 h-4" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(it)} data-testid={`catering-delete-${idx}`}><Trash2 className="w-4 h-4" /></Button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {!items.length && (
              <tr><td colSpan={canManage ? 5 : 4} className="px-3 py-6 text-center text-[#9CA3AF]">Keine Artikel.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
