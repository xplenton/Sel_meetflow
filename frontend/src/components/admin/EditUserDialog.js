import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { X } from 'lucide-react';
import api from '../../lib/api';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * EditUserDialog (iter 340) — admin edits a user's master data + role +
 * group memberships.
 *
 * BenutzerID (`user.user_id`) wird oben read-only angezeigt; alle anderen
 * Stammdaten (Vor-/Nachname, Anzeigename, Telefon, Abteilung) sind editierbar.
 */
export default function EditUserDialog({ user, onClose, onSave }) {
  const { t } = useLanguage();
  const [role, setRole] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [phone, setPhone] = useState('');
  const [dept, setDept] = useState('');
  const [location, setLocation] = useState('');
  const [profession, setProfession] = useState('');
  const [orgUnit, setOrgUnit] = useState('');
  const [personnelNumber, setPersonnelNumber] = useState('');
  const [selectedGroups, setSelectedGroups] = useState([]);
  const [groups, setGroups] = useState([]);

  useEffect(() => {
    if (user) {
      setRole(user.role || '');
      setFirstName(user.first_name || '');
      setLastName(user.last_name || '');
      setDisplayName(user.display_name || '');
      setPhone(user.phone || '');
      setDept(user.department || '');
      setLocation(user.location || '');
      setProfession(user.profession || '');
      setOrgUnit(user.org_unit || '');
      // Iter 366 — Personalnummer
      setPersonnelNumber(user.personnel_number || '');
      setSelectedGroups(Array.isArray(user.groups) ? user.groups : []);
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    api.get('/admin/groups')
      .then(r => setGroups(Array.isArray(r.data) ? r.data : (r.data?.groups || [])))
      .catch(() => setGroups([]));
  }, [user]);

  const addGroup = (gid) => {
    if (!gid || selectedGroups.includes(gid)) return;
    setSelectedGroups([...selectedGroups, gid]);
  };
  const removeGroup = (gid) => setSelectedGroups(selectedGroups.filter(g => g !== gid));
  const remainingGroups = groups.filter(g => !selectedGroups.includes(g.group_id));

  const handleSave = () => {
    onSave({
      role,
      first_name: firstName,
      last_name: lastName,
      display_name: displayName,
      phone,
      department: dept,
      location,
      profession,
      org_unit: orgUnit,
      personnel_number: personnelNumber,
      groups: selectedGroups,
    });
  };

  return (
    <Dialog open={!!user} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base font-medium">
            Profil: {user?.display_name || user?.name}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          {/* Iter 340 — BenutzerID read-only sichtbar machen. */}
          <div className="bg-[#F3F4F1] rounded-lg p-2.5 flex items-center justify-between">
            <span className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider">BenutzerID</span>
            <span className="font-mono text-[11px] text-[#4A5D4E]" data-testid="edit-user-id">{user?.user_id}</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Vorname</label>
              <Input value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="Max"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-first-name-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Nachname</label>
              <Input value={lastName} onChange={e => setLastName(e.target.value)} placeholder="Mustermann"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-last-name-input" />
            </div>
            <div className="col-span-2">
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Anzeigename</label>
              <Input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="optional"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-display-name-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Telefonnummer</label>
              <Input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+49 …"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-phone-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Rolle</label>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Administrator</SelectItem>
                  <SelectItem value="moderator">Moderator</SelectItem>
                  <SelectItem value="member">Mitarbeiter</SelectItem>
                  <SelectItem value="guest">Gast</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Abteilung</label>
              <Input value={dept} onChange={e => setDept(e.target.value)} placeholder="z.B. Innere Medizin"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-department-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Standort</label>
              <Input value={location} onChange={e => setLocation(e.target.value)} placeholder="z.B. Standort Nord"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-location-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{t('profession')}</label>
              <Input value={profession} onChange={e => setProfession(e.target.value)} placeholder="z.B. Pflege / Arzt"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-profession-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{t('orgUnit')}</label>
              <Input value={orgUnit} onChange={e => setOrgUnit(e.target.value)} placeholder="z.B. Station 3B"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-orgunit-input" />
            </div>
            {/* Iter 366 — Personalnummer als Stammdaten-Feld. */}
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Personalnummer</label>
              <Input value={personnelNumber} onChange={e => setPersonnelNumber(e.target.value)} placeholder="z.B. 10024"
                className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-personnel-number-input" />
            </div>
          </div>
          {/* Iter 340 — Gruppen-Mitgliedschaft direkt im Profil editierbar. */}
          {/* Iter 379 — System-managed Module-Gruppen (`Modul: *`) werden
              hier ausgeblendet. Sie werden automatisch per Rolle vergeben
              (`sync_user_module_groups`) und lassen sich vom Admin nicht
              dauerhaft entfernen — die Sichtbarkeit als Chip war daher
              verwirrend ("ich kann Modul:Standard nicht entfernen"). */}
          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Gruppen</label>
            {(() => {
              const visibleSelected = selectedGroups.filter(gid => {
                const g = groups.find(x => x.group_id === gid);
                return g ? !g.module_group : true;
              });
              const visibleRemaining = remainingGroups.filter(g => !g.module_group);
              return (
                <>
                  {visibleSelected.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2" data-testid="edit-selected-groups">
                      {visibleSelected.map(gid => {
                        const g = groups.find(x => x.group_id === gid);
                        return (
                          <Badge key={gid} variant="outline" className="gap-1 bg-[#4A5D4E]/5 border-[#4A5D4E]/30" data-testid={`edit-group-chip-${gid}`}>
                            {g?.name || gid}
                            <button type="button" onClick={() => removeGroup(gid)} className="ml-1 text-[#6B7280] hover:text-rose-600">
                              <X className="w-3 h-3" />
                            </button>
                          </Badge>
                        );
                      })}
                    </div>
                  )}
                  {visibleRemaining.length > 0 ? (
                    <Select value="" onValueChange={addGroup}>
                      <SelectTrigger className="border-[#E2E4E0] rounded-xl text-sm" data-testid="edit-group-add-select">
                        <SelectValue placeholder="Gruppe hinzufügen…" />
                      </SelectTrigger>
                      <SelectContent>
                        {visibleRemaining.map(g => (
                          <SelectItem key={g.group_id} value={g.group_id} data-testid={`edit-group-option-${g.group_id}`}>
                            {g.name}{g.description ? ` — ${g.description}` : ''}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : visibleSelected.length === 0 ? (
                    <p className="text-[11px] text-[#9CA3AF]">Keine Gruppen vorhanden.</p>
                  ) : (
                    <p className="text-[11px] text-[#9CA3AF]">Alle Gruppen ausgewählt.</p>
                  )}
                  <p className="text-[10px] text-[#9CA3AF] mt-1.5">
                    Modul-Sichtbarkeit (Dashboard, Verwaltung, …) wird automatisch über die Rolle gesteuert und nicht hier verwaltet.
                  </p>
                </>
              );
            })()}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
          <Button onClick={handleSave} data-testid="confirm-edit-role"
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full">Speichern</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
