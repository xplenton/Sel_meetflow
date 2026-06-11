import { useState, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import SignaturePad from './SignaturePad';
import {
  PenTool, Plus, Trash2, CheckCircle, Circle, Users, X
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
export default function SignatureFieldsPanel({
  meetingId, docId, isHost, userId, userName, participants, onSignField
}) {
  const { t } = useLanguage();
  const [fields, setFields] = useState([]);
  const [total, setTotal] = useState(0);
  const [signed, setSigned] = useState(0);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [signDialogOpen, setSignDialogOpen] = useState(false);
  const [signingField, setSigningField] = useState(null);
  const [newField, setNewField] = useState({ x: 100, y: 400, page: 1, label: 'Unterschrift', assigned_to: '', assigned_name: '' });

  const fetchFields = useCallback(async () => {
    try {
      const { data } = await api.get(`/meetings/${meetingId}/documents/${docId}/signature-fields`);
      setFields(data.fields || []);
      setTotal(data.total || 0);
      setSigned(data.signed || 0);
    } catch {}
  }, [meetingId, docId]);

  useEffect(() => { fetchFields(); }, [fetchFields]);

  const handleAddField = async () => {
    try {
      await api.post(`/meetings/${meetingId}/documents/${docId}/signature-fields`, newField);
      flushSync(() => {
        setAddDialogOpen(false);
        setNewField({ x: 100, y: 400, page: 1, label: 'Unterschrift', assigned_to: '', assigned_name: '' });
      });
      setTimeout(() => { toast.success('Signaturfeld hinzugefügt'); }, 50);
      fetchFields();
    } catch {
      toast.error('Fehler beim Hinzufügen');
    }
  };

  const handleDeleteField = async (fieldId) => {
    try {
      await api.delete(`/meetings/${meetingId}/documents/${docId}/signature-fields/${fieldId}`);
      fetchFields();
    } catch {}
  };

  const openSignForField = (field) => {
    setSigningField(field);
    setSignDialogOpen(true);
  };

  const handleSignField = async (sigData) => {
    if (!signingField) return;
    const fieldData = {
      ...sigData,
      field_id: signingField.field_id,
      pos_x: signingField.x,
      pos_y: signingField.y,
      page: signingField.page,
    };
    flushSync(() => {
      setSignDialogOpen(false);
      setSigningField(null);
    });
    // Pass to parent after dialog cleanup
    setTimeout(() => {
      onSignField(fieldData);
      setTimeout(fetchFields, 1000);
    }, 50);
  };

  const myFields = fields.filter(f => !f.assigned_to || f.assigned_to === userId);
  const canSign = (f) => f.status === 'pending' && (!f.assigned_to || f.assigned_to === userId);

  return (
    <div className="space-y-3" data-testid="signature-fields-panel">
      {/* Progress */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PenTool className="w-3.5 h-3.5 text-[#4A5D4E]" />
          <span className="text-xs font-medium text-[#1C1F1D]">Signaturfelder</span>
        </div>
        <Badge className={`text-[9px] ${signed === total && total > 0 ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280]'}`}
          data-testid="sig-fields-progress">
          {signed}/{total} unterschrieben
        </Badge>
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="h-1.5 bg-[#E2E4E0] rounded-full overflow-hidden" data-testid="sig-fields-progress-bar">
          <div className="h-full bg-[#4A5D4E] rounded-full transition-all duration-500"
            style={{ width: `${total > 0 ? (signed / total) * 100 : 0}%` }} />
        </div>
      )}

      {/* Add field button (host only) */}
      {isHost && (
        <Button size="sm" variant="outline" onClick={() => setAddDialogOpen(true)}
          className="w-full text-[10px] h-7 border-dashed border-[#4A5D4E]/30 text-[#4A5D4E]"
          data-testid="add-signature-field-btn">
          <Plus className="w-3 h-3 mr-1" />Signaturfeld hinzufügen
        </Button>
      )}

      {/* Fields list */}
      <ScrollArea className="max-h-48">
        <div className="space-y-1.5">
          {fields.map((f, i) => (
            <div key={f.field_id}
              className={`flex items-center gap-2 p-2 rounded-lg border transition-colors ${
                f.status === 'signed' ? 'border-[#4A5D4E]/20 bg-[#4A5D4E]/5' : 'border-[#E2E4E0]'
              }`}
              data-testid={`sig-field-${f.field_id}`}>
              {f.status === 'signed' ? (
                <CheckCircle className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
              ) : (
                <Circle className="w-3.5 h-3.5 text-[#9CA3AF] flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-medium text-[#1C1F1D] truncate">{f.label}</p>
                <p className="text-[8px] text-[#9CA3AF]">
                  {f.assigned_name || 'Alle'} — Seite {f.page}
                  {f.status === 'signed' && f.signed_by && ` — ${f.signed_by}`}
                </p>
              </div>
              {canSign(f) && (
                <Button size="sm" variant="ghost" onClick={() => openSignForField(f)}
                  className="h-5 px-1.5 text-[8px] text-[#4A5D4E]" data-testid={`sign-field-${f.field_id}`}>
                  <PenTool className="w-2.5 h-2.5 mr-0.5" />Sign
                </Button>
              )}
              {isHost && f.status === 'pending' && (
                <button onClick={() => handleDeleteField(f.field_id)}
                  className="p-0.5 text-[#9CA3AF] hover:text-[#C87967]" data-testid={`delete-field-${f.field_id}`}>
                  <Trash2 className="w-2.5 h-2.5" />
                </button>
              )}
            </div>
          ))}
          {fields.length === 0 && (
            <p className="text-[10px] text-[#9CA3AF] text-center py-2">{t('noSignatureFieldsDefined')}</p>
          )}
        </div>
      </ScrollArea>

      {/* Add Field Dialog */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent className="sm:max-w-sm" data-testid="add-field-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">{t('addSignatureField')}</DialogTitle>
            <DialogDescription className="text-xs text-[#9CA3AF]">
              Definieren Sie, wo unterschrieben werden soll
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-[10px] text-[#6B7280] block mb-1">Bezeichnung</label>
              <Input value={newField.label} onChange={(e) => setNewField(p => ({ ...p, label: e.target.value }))}
                className="text-xs h-8" placeholder="z.B. Unterschrift Auftragnehmer" data-testid="field-label-input" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="text-[10px] text-[#6B7280] block mb-1">Seite</label>
                <Input type="number" min={1} value={newField.page}
                  onChange={(e) => setNewField(p => ({ ...p, page: parseInt(e.target.value) || 1 }))}
                  className="text-xs h-8" data-testid="field-page-input" />
              </div>
              <div>
                <label className="text-[10px] text-[#6B7280] block mb-1">X</label>
                <Input type="number" min={0} value={newField.x}
                  onChange={(e) => setNewField(p => ({ ...p, x: parseInt(e.target.value) || 0 }))}
                  className="text-xs h-8" data-testid="field-x-input" />
              </div>
              <div>
                <label className="text-[10px] text-[#6B7280] block mb-1">Y</label>
                <Input type="number" min={0} value={newField.y}
                  onChange={(e) => setNewField(p => ({ ...p, y: parseInt(e.target.value) || 0 }))}
                  className="text-xs h-8" data-testid="field-y-input" />
              </div>
            </div>
            {participants?.length > 0 && (
              <div>
                <label className="text-[10px] text-[#6B7280] block mb-1">Zuweisen an</label>
                <Select value={newField.assigned_to || 'all'}
                  onValueChange={(v) => {
                    const p = participants.find(pt => pt.user_id === v);
                    setNewField(prev => ({ ...prev, assigned_to: v === 'all' ? '' : v, assigned_name: p?.name || '' }));
                  }}>
                  <SelectTrigger className="text-xs h-8" data-testid="field-assign-select">
                    <SelectValue placeholder="Alle Teilnehmer" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all" className="text-xs">{t('allParticipants')}</SelectItem>
                    {participants.map(p => (
                      <SelectItem key={p.user_id} value={p.user_id} className="text-xs">{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setAddDialogOpen(false)} className="text-xs h-7">
                Abbrechen
              </Button>
              <Button size="sm" onClick={handleAddField}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs h-7" data-testid="confirm-add-field">
                <Plus className="w-3 h-3 mr-1" />Hinzufügen
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Sign Field Dialog */}
      <Dialog open={signDialogOpen} onOpenChange={setSignDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="sign-field-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">{signingField?.label || 'Unterschrift'}</DialogTitle>
            <DialogDescription className="text-xs text-[#9CA3AF]">
              Seite {signingField?.page}, Position ({signingField?.x}, {signingField?.y})
            </DialogDescription>
          </DialogHeader>
          <SignaturePad
            signerName={userName}
            onSign={handleSignField}
            onCancel={() => { setSignDialogOpen(false); setSigningField(null); }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
