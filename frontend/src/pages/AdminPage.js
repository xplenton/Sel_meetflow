import { copyToClipboard } from '../lib/clipboard';
import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import { useAuth } from '../contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '../components/ui/alert-dialog';
import {
  Users, BarChart3, Video, MessageSquare, Disc, Search, Shield,
  Paintbrush, ScrollText, Key, UserPlus, Upload, Building2,
  Flag, FileSearch, KeyRound, Sparkles, Zap, Power,
  Heart, Stethoscope, ShieldCheck, Settings, Car, FileText, Download, HardDrive,
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import BrandingSettings from '../components/BrandingSettings';
import BulkInviteDialog from '../components/BulkInviteDialog';
import BulkUserImportDialog from '../components/admin/BulkUserImportDialog';
import NewsModerationPanel from '../components/NewsModerationPanel';
import AuditLogPanel from '../components/AuditLogPanel';
import QuickScansPanel from '../components/QuickScansPanel';
import ApiConfigPanel from '../components/admin/ApiConfigPanel';
import LiveKitConfigPanel from '../components/admin/LiveKitConfigPanel';
import BrandingPanel from '../components/admin/BrandingPanel';
import EmailConfigPanel from '../components/admin/EmailConfigPanel';
import SsoConfigPanel from '../components/admin/SsoConfigPanel';
import PoliciesPanel from '../components/admin/PoliciesPanel';
import ReminderConfigPanel from '../components/admin/ReminderConfigPanel';
import GroupsPanel from '../components/admin/GroupsPanel';
import ResourcesAdminPanel from '../components/admin/ResourcesAdminPanel';
import RolesCapsPanel from '../components/admin/RolesCapsPanel';
import PresetEditorPanel from '../components/admin/PresetEditorPanel';
import AutoAssignRulesPanel from '../components/admin/AutoAssignRulesPanel';
import HealthDashboard from '../components/admin/HealthDashboard';
import SystemAuditPanel from '../components/admin/SystemAuditPanel';
import DriversLicenseAdminPanel from '../components/admin/DriversLicenseAdminPanel';
import InvoiceConfigPanel from '../components/admin/InvoiceConfigPanel';
import PermissionsHub from '../components/admin/PermissionsHub';
import EditUserDialog from '../components/admin/EditUserDialog';
import InviteUserDialog from '../components/admin/InviteUserDialog';
import AdminUserRow from '../components/admin/AdminUserRow';
import FiletransferStorageSettings from '../components/filetransfer/StorageSettings';

export default function AdminPage() {
  const { t } = useLanguage();
  const { user: currentUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [editUser, setEditUser] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [bulkInviteOpen, setBulkInviteOpen] = useState(false);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    // Iter 374 — alle Stammdaten- und Profil-Felder + Direct-Caps initialisiert,
    // damit das InviteUserDialog die Pflichtfeld-Validierung sauber prüfen kann.
    email: '', name: '', first_name: '', last_name: '', display_name: '',
    phone: '', department: '', position: '', personnel_number: '',
    location: '', profession: '', org_unit: '', language: 'de',
    role: 'member', group_ids: [], cap_grants: [], cap_denies: [],
    // Iter 379 — Toggle "Kein E-Mail-Konto" + Initial-Passwort für No-Email-User.
    no_email: false, initial_password: '',
  });
  const [inviteResult, setInviteResult] = useState(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [filterRole, setFilterRole] = useState('all');
  const [filterDept, setFilterDept] = useState('all');
  const [filterLocation, setFilterLocation] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  // Iter 379 — Sortier-Option für die Personen-Liste. Default „created"
  // entspricht dem bisherigen Server-Order (DESC). Sortierung erfolgt
  // client-seitig auf der bereits geladenen Page, damit das Backend nichts
  // anpassen muss.
  const [sortBy, setSortBy] = useState('created');

  const isAdminish = currentUser?.role === 'admin' || currentUser?.role === 'moderator';

  // ============ React Query: admin lists (iter 118) ============
  // `enabled: isAdminish` skips requests for non-admins (previously produced
  // toast spam of 403s). Query keys include filter state so filter changes
  // produce a new query (with a brief staleTime grace period that behaves
  // like our old 250ms debounce).
  // Debounce search: only push to query-key once input settles for 250ms
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const h = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(h);
  }, [search]);
  // Reset to page 1 whenever any filter/search changes
  useEffect(() => { setPage(1); }, [debouncedSearch, filterRole, filterDept, filterLocation, filterStatus]);

  const userParams = useMemo(() => {
    const p = { page, limit };
    if (debouncedSearch) p.search = debouncedSearch;
    if (filterRole !== 'all') p.role = filterRole;
    if (filterDept !== 'all') p.department = filterDept;
    if (filterLocation !== 'all') p.location = filterLocation;
    if (filterStatus !== 'all') p.status = filterStatus;
    return p;
  }, [page, limit, debouncedSearch, filterRole, filterDept, filterLocation, filterStatus]);

  const usersQ = useQuery({
    queryKey: ['admin', 'users', userParams],
    queryFn: async () => (await api.get('/admin/users', { params: userParams })).data,
    enabled: !!isAdminish,
    keepPreviousData: true,
  });
  const statsQ = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: async () => (await api.get('/admin/stats')).data,
    enabled: !!isAdminish,
  });
  // Iter 291 — fetch auto-lock-hours so the verification badge can show the
  // remaining grace time in the row.
  const orgSettingsQ = useQuery({
    queryKey: ['admin', 'org-settings'],
    queryFn: async () => (await api.get('/admin/org-settings')).data,
    enabled: !!isAdminish,
    staleTime: 60_000,
  });
  const autoLockHours = orgSettingsQ.data?.auto_lock_unverified_hours ?? 24;
  const groupsQ = useQuery({
    queryKey: ['admin', 'groups'],
    queryFn: async () => (await api.get('/admin/groups')).data,
    enabled: !!isAdminish,
  });
  const filtersQ = useQuery({
    queryKey: ['admin', 'user-filters'],
    queryFn: async () => (await api.get('/admin/users/filters')).data,
    enabled: !!isAdminish,
    staleTime: 5 * 60_000,
  });
  const allUsersQ = useQuery({
    queryKey: ['admin', 'users-all'],
    queryFn: async () => {
      const { data } = await api.get('/admin/users');
      return Array.isArray(data) ? data : (data?.users || []);
    },
    enabled: !!isAdminish,
    staleTime: 60_000,
  });

  // Normalise the paginated users response
  const usersPayload = usersQ.data;
  const users = Array.isArray(usersPayload?.users) ? usersPayload.users : (Array.isArray(usersPayload) ? usersPayload : []);
  const total = usersPayload?.total ?? users.length;
  const pages = usersPayload?.pages ?? 1;
  const stats = statsQ.data;
  const groups = groupsQ.data || [];
  const filterOptions = filtersQ.data || { departments: [], locations: [], roles: [] };
  const allUsers = allUsersQ.data || [];
  const loading = usersQ.isLoading || statsQ.isLoading;

  // ----- toast on first 403/401 (non-admin deep-linked) -----
  useEffect(() => {
    const err = usersQ.error || statsQ.error;
    if (!err) return;
    const code = err?.response?.status;
    if (code !== 401 && code !== 403) toast.error('Verwaltungsdaten konnten nicht geladen werden');
  }, [usersQ.error, statsQ.error]);

  // After any admin mutation, invalidating these keys makes every list on
  // the page refetch automatically — users no longer need to press F5
  // (iter 118 fix). Centralised here so individual handlers stay terse.
  const invalidateAdminLists = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    qc.invalidateQueries({ queryKey: ['admin', 'users-all'] });
    qc.invalidateQueries({ queryKey: ['admin', 'stats'] });
    qc.invalidateQueries({ queryKey: ['admin', 'groups'] });
    qc.invalidateQueries({ queryKey: ['admin', 'user-filters'] });
  };

  const updateUserMutation = useMutation({
    mutationFn: ({ user_id, body }) => api.put(`/admin/users/${user_id}`, body),
    onSuccess: () => { toast.success('Profil aktualisiert'); invalidateAdminLists(); setEditUser(null); },
    onError: () => toast.error('Fehler beim Aktualisieren'),
  });
  const deleteUserMutation = useMutation({
    mutationFn: (user_id) => api.delete(`/admin/users/${user_id}`),
    onSuccess: () => { toast.success('Nutzer gelöscht'); invalidateAdminLists(); setDeleteConfirm(null); },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler beim Löschen'),
  });
  const inviteUserMutation = useMutation({
    mutationFn: (form) => api.post('/admin/users/invite', form),
    onSuccess: ({ data }) => {
      setInviteResult(data);
      if (data.email_sent) toast.success(`Einladung an ${data.email} gesendet!`);
      else toast.success('Benutzer erstellt (E-Mail konnte nicht gesendet werden)');
      setInviteForm({
        email: '', name: '', first_name: '', last_name: '', display_name: '',
        phone: '', department: '', position: '', personnel_number: '',
        location: '', profession: '', org_unit: '', language: 'de',
        role: 'member', group_ids: [], cap_grants: [], cap_denies: [],
      });
      invalidateAdminLists();
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });
  const toggleStatusMutation = useMutation({
    mutationFn: (user_id) => api.put(`/admin/users/${user_id}/status`),
    onSuccess: ({ data }) => {
      toast.success(`Status: ${data.status === 'active' ? 'Aktiv' : 'Deaktiviert'}`);
      invalidateAdminLists();
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });

  const handleUpdateRole = (body) => {
    if (!editUser) return;
    updateUserMutation.mutate({ user_id: editUser.user_id, body });
  };
  const handleDelete = () => deleteConfirm && deleteUserMutation.mutate(deleteConfirm.user_id);
  const handleInvite = () => {
    // Iter 379 — Bei "Kein E-Mail-Konto" ist E-Mail nicht Pflicht; das
    // InviteUserDialog selbst validiert Personalnummer + Initial-Passwort.
    if (!inviteForm.no_email && !inviteForm.email.trim()) {
      toast.error('E-Mail erforderlich'); return;
    }
    inviteUserMutation.mutate(inviteForm);
  };
  const handleToggleStatus = (userId) => toggleStatusMutation.mutate(userId);

  const handleForceLogoutUser = async (u) => {
    if (!window.confirm(`Wirklich alle Sessions von "${u.name || u.email}" beenden? Der Nutzer muss sich neu einloggen.`)) return;
    try {
      await api.post(`/admin/users/${u.user_id}/force-logout`);
      toast.success(`Sessions beendet: ${u.email}`);
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler beim Abmelden'); }
  };

  const [forceLogoutAllLoading, setForceLogoutAllLoading] = useState(false);
  const handleForceLogoutAll = async () => {
    // AlertDialog has already confirmed — just fire and report the outcome clearly
    setForceLogoutAllLoading(true);
    try {
      const { data } = await api.post('/admin/force-logout-all');
      const count = typeof data?.modified_count === 'number' ? data.modified_count : 0;
      if (count > 0) {
        toast.success(`${count} ${count === 1 ? 'Nutzer wurde' : 'Nutzer wurden'} abgemeldet`);
      } else {
        toast.info('Keine weiteren aktiven Sessions gefunden');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Force-Logout fehlgeschlagen');
    } finally {
      setForceLogoutAllLoading(false);
    }
  };

  // Server-side pagination + filters already applied → render users as-is
  // Iter 379 — Sortierung clientseitig anwenden, damit das Backend keine
  // Order-Änderung braucht. „pw_oldest" listet zuerst die User mit dem
  // aeltesten (oder fehlendem) Passwort-Wechsel — wichtig für
  // Compliance-Audits.
  const filtered = useMemo(() => {
    const list = [...(users || [])];
    if (sortBy === 'name_asc') {
      list.sort((a, b) => (a.name || a.email || '').localeCompare(b.name || b.email || ''));
    } else if (sortBy === 'last_seen_desc') {
      list.sort((a, b) => (new Date(b.last_seen || 0).getTime()) - (new Date(a.last_seen || 0).getTime()));
    } else if (sortBy === 'pw_oldest') {
      // Fehlendes `password_changed_at` zuerst (= unbekannt/Compliance-Risiko).
      const ts = (u) => u.password_changed_at ? new Date(u.password_changed_at).getTime() : 0;
      list.sort((a, b) => ts(a) - ts(b));
    } else if (sortBy === 'pw_newest') {
      const ts = (u) => u.password_changed_at ? new Date(u.password_changed_at).getTime() : Number.MAX_SAFE_INTEGER;
      list.sort((a, b) => ts(b) - ts(a));
    }
    return list;
  }, [users, sortBy]);
  const getUserGroups = (userId) => groups.filter(g => (g.members || []).includes(userId));

  const roleColors = {
    admin: 'bg-[#4A5D4E]/10 text-[#4A5D4E]',
    manager: 'bg-[#D4A373]/10 text-[#D4A373]',
    member: 'bg-[#6B8E23]/10 text-[#6B8E23]',
    guest: 'bg-[#9CA3AF]/10 text-[#9CA3AF]',
    user: 'bg-[#9CA3AF]/10 text-[#9CA3AF]',
    host: 'bg-[#D4A373]/10 text-[#D4A373]',
    'co-host': 'bg-[#6B8E23]/10 text-[#6B8E23]',
  };

  const statCards = stats ? [
    { label: t('totalUsers'), value: stats.total_users, icon: Users, color: 'text-[#4A5D4E]' },
    { label: t('totalMeetings'), value: stats.total_meetings, icon: Video, color: 'text-[#D4A373]' },
    { label: t('activeMeetings'), value: stats.active_meetings, icon: BarChart3, color: 'text-[#6B8E23]' },
    { label: t('totalMessages'), value: stats.total_messages, icon: MessageSquare, color: 'text-[#9CA3AF]' },
    { label: t('endedMeetings'), value: stats.ended_meetings, icon: Disc, color: 'text-[#C87967]' },
    { label: t('polls'), value: stats.total_polls, icon: BarChart3, color: 'text-[#4A5D4E]' },
  ] : [];

  if (currentUser?.role !== 'admin') {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 flex items-center justify-center">
          <div className="text-center">
            <Shield className="w-12 h-12 text-[#C87967] mx-auto mb-3" />
            <h2 className="text-lg font-medium text-[#1C1F1D]">{t('adminAccessRequired')}</h2>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:p-8 animate-fade-in" data-testid="admin-page">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-xl sm:text-2xl font-medium tracking-tight mb-5 sm:mb-6 text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('admin')}</h1>

          {/* Iter 396 — Default-Tab von 'stats' auf 'users' geändert, weil
              Statistiken in die Auswertungen verschoben wurden. Legacy-Links
              mit ?tab=stats / drivers-licenses / news-moderation leiten weiter
              unten (in einem useEffect) auf /analytics um. */}
          <Tabs value={searchParams.get('tab') || 'users'} onValueChange={(v) => setSearchParams(v === 'users' ? {} : { tab: v })}>
            {/* iter 212 — group the 16 admin tabs into 4 logical buckets so
                the tab bar isn't a horizontal scroll-wall. The active group
                is derived from the active tab so deep-links keep working. */}
            {(() => {
              const TAB_GROUPS = [
                {
                  id: 'people', label: '👥 Personen', icon: Users,
                  tabs: [
                    { value: 'users', label: t('userManagement') },
                    { value: 'groups', label: t('groups'), icon: Building2 },
                    { value: 'auto-rules', label: 'Auto-Regeln', icon: Zap },
                  ],
                },
                {
                  id: 'rights', label: '🔐 Rechte', icon: ShieldCheck,
                  tabs: [
                    { value: 'permissions', label: 'Berechtigungs-Hub', icon: ShieldCheck },
                    { value: 'roles-caps', label: t('rolesAndRights'), icon: KeyRound },
                    { value: 'presets', label: 'Presets', icon: Sparkles },
                  ],
                },
                {
                  id: 'system', label: '⚙️ System', icon: Settings,
                  tabs: [
                    { value: 'branding', label: t('branding'), icon: Paintbrush },
                    { value: 'integrations', label: t('integrations'), icon: Key },
                    { value: 'sso', label: 'SSO', icon: ShieldCheck },
                    { value: 'reminders', label: t('reminders') },
                    { value: 'policies', label: t('policies'), icon: ScrollText },
                    { value: 'resources-admin', label: 'Ressourcen', icon: Building2 },
                    { value: 'invoice-config', label: 'Rechnungen-Setup', icon: FileText },
                    { value: 'filetransfer-storage', label: 'Filetransfer-Speicher', icon: HardDrive },
                  ],
                },
                {
                  id: 'monitoring', label: '📊 Monitoring', icon: BarChart3,
                  tabs: [
                    // Iter 396 — Statistiken, Führerscheine und News-Moderation
                    // wurden in die Auswertungen (/analytics) verschoben, damit
                    // alle auswertbaren Daten zentral an einem Ort liegen.
                    { value: 'health', label: 'Health', icon: Heart },
                    { value: 'quick-scans', label: 'Quick-Scans', icon: Stethoscope },
                    { value: 'audit-log', label: 'Audit-Log', icon: FileSearch },
                    { value: 'system-audit', label: 'System-Audit', icon: Shield },
                  ],
                },
              ];
              const activeTab = searchParams.get('tab') || 'stats';
              const activeGroup = TAB_GROUPS.find(g => g.tabs.some(t => t.value === activeTab))
                || TAB_GROUPS.find(g => g.id === 'monitoring');
              return (
                <>
                  {/* Mobile: dropdown navigation (<640px) */}
                  <div className="sm:hidden mb-4">
                    <Select value={activeTab} onValueChange={(v) => setSearchParams(v === 'stats' ? {} : { tab: v })}>
                      <SelectTrigger className="border-[#E2E4E0] rounded-lg" data-testid="admin-tab-mobile-select">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TAB_GROUPS.map(g => (
                          <div key={g.id}>
                            <div className="px-2 py-1 text-[10px] font-semibold text-[#9CA3AF] uppercase">{g.label}</div>
                            {g.tabs.map(tb => (
                              <SelectItem key={tb.value} value={tb.value}>{tb.label}</SelectItem>
                            ))}
                          </div>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {/* Tablet/Desktop: 2-row group + sub-tab navigation */}
                  <div className="hidden sm:block mb-6 space-y-2">
                    {/* Row 1: Top-level groups */}
                    <div className="flex items-center gap-1 border-b border-[#E2E4E0] pb-1.5">
                      {TAB_GROUPS.map(g => {
                        const GIcon = g.icon;
                        const isActive = activeGroup.id === g.id;
                        return (
                          <button key={g.id}
                            onClick={() => {
                              // Switch to first sub-tab in the group when changing groups
                              const first = g.tabs[0].value;
                              setSearchParams(first === 'stats' ? {} : { tab: first });
                            }}
                            className={`px-3 py-1.5 text-xs font-medium rounded-md flex items-center gap-1.5 transition ${isActive ? 'bg-[#1A1D1B] text-white' : 'text-[#6B7280] hover:bg-[#F5F4F0]'}`}
                            data-testid={`admin-group-${g.id}`}>
                            <GIcon className="w-3.5 h-3.5" />{g.label}
                          </button>
                        );
                      })}
                    </div>
                    {/* Row 2: Sub-tabs of the active group */}
                    <div className="overflow-x-auto scrollbar-thin">
                      <TabsList className="bg-[#F3F4F1] rounded-lg justify-start w-max min-w-full">
                        {activeGroup.tabs.map(tb => {
                          const TIcon = tb.icon;
                          return (
                            <TabsTrigger key={tb.value} value={tb.value}
                              data-testid={`admin-tab-${tb.value}`}
                              className="rounded-lg text-sm whitespace-nowrap">
                              {TIcon && <TIcon className="w-3.5 h-3.5 mr-1" />}{tb.label}
                            </TabsTrigger>
                          );
                        })}
                      </TabsList>
                    </div>
                  </div>
                </>
              );
            })()}

            <TabsContent value="stats">
              {/* Iter 396 — Legacy-Redirect: Deeplinks mit ?tab=stats kommen
                  von Bookmarks/Notifications etc. Statt 404 verweisen wir
                  freundlich auf den neuen Ort. */}
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center" data-testid="stats-moved-notice">
                <BarChart3 className="w-10 h-10 text-[#9CA3AF] mx-auto mb-3" />
                <p className="text-sm text-[#1C1F1D] font-medium mb-1">Statistiken sind umgezogen</p>
                <p className="text-xs text-[#6B7280] mb-4">Du findest sie jetzt unter <strong>Auswertungen</strong>.</p>
                <a href="/analytics?tab=stats" className="inline-flex items-center gap-1 text-xs font-medium text-[#4A5D4E] hover:underline">Zu den Statistiken &rarr;</a>
              </div>
            </TabsContent>

            <TabsContent value="health">
              <HealthDashboard />
            </TabsContent>

            <TabsContent value="permissions" data-testid="permissions-hub-content">
              <PermissionsHub />
            </TabsContent>

            <TabsContent value="users">
              <div className="bg-white border border-[#E2E4E0] rounded-xl">
                <div className="p-4 border-b border-[#E2E4E0] flex flex-wrap items-center gap-3">
                  <div className="relative flex-1 min-w-[200px]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                    <Input data-testid="admin-search-users" value={search} onChange={e => setSearch(e.target.value)}
                      placeholder={t('search')} className="pl-10 border-[#E2E4E0] rounded-lg" />
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="outline"
                        className="rounded-full text-xs flex-shrink-0 border-[#C87967]/40 text-[#C87967] hover:bg-[#C87967]/10"
                        data-testid="force-logout-all-btn"
                        title={t('logoutAllConfirm')}
                        disabled={forceLogoutAllLoading}
                      >
                        <Power className="w-3.5 h-3.5 mr-1" /> {t('logoutAll')}
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent data-testid="force-logout-all-dialog">
                      <AlertDialogHeader>
                        <AlertDialogTitle className="text-[#C87967] flex items-center gap-2">
                          <Power className="w-5 h-5" /> {t('logoutAll')}?
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-xs text-[#6B7280] space-y-2 pt-1">
                          Alle aktiven Nutzer <strong>außer dir</strong> werden sofort abgemeldet und müssen sich neu anmelden. Laufende Video-Meetings, Chats und Ticket-Bearbeitungen werden unterbrochen.
                          <br /><br />
                          Typisch genutzt nach Security-Incidents oder Cookie-Rotation. <strong>Fortfahren?</strong>
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel data-testid="force-logout-all-cancel">Abbrechen</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={handleForceLogoutAll}
                          disabled={forceLogoutAllLoading}
                          data-testid="force-logout-all-confirm"
                          className="bg-[#C87967] hover:bg-[#B5624F] text-white"
                        >
                          {forceLogoutAllLoading ? '...' : 'Ja, alle abmelden'}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                  <Button onClick={() => setBulkInviteOpen(true)} variant="outline" className="rounded-full text-xs flex-shrink-0 border-[#6B8E23]/40 text-[#6B8E23] hover:bg-[#6B8E23]/10" data-testid="bulk-invite-btn">
                    <Upload className="w-3.5 h-3.5 mr-1" /> {t('bulkInvite')}
                  </Button>
                  {/* Iter 342 — CSV-Export aller User (gleiche Spalten wie Import). */}
                  <Button onClick={async () => {
                    try {
                      const res = await api.get('/admin/users/export.csv', { responseType: 'blob' });
                      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
                      const a = document.createElement('a');
                      a.href = url;
                      const m = res.headers?.['content-disposition']?.match(/filename="([^"]+)"/);
                      a.download = m?.[1] || 'meetflow-users.csv';
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch (e) {
                      toast.error('Export fehlgeschlagen');
                    }
                  }} variant="outline" className="rounded-full text-xs flex-shrink-0 border-[#4A5D4E]/40 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid="csv-export-btn">
                    <Download className="w-3.5 h-3.5 mr-1" /> CSV-Export
                  </Button>
                  {/* Iter 341 — CSV-Bulk-Import mit voller Stammdaten-Erweiterung. */}
                  <Button onClick={() => setBulkImportOpen(true)} variant="outline" className="rounded-full text-xs flex-shrink-0 border-[#4A5D4E]/40 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid="bulk-import-btn">
                    <FileText className="w-3.5 h-3.5 mr-1" /> CSV-Import
                  </Button>
                  <Button onClick={() => setInviteOpen(true)} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs flex-shrink-0" data-testid="invite-user-btn">
                    <UserPlus className="w-3.5 h-3.5 mr-1" /> {t('invite')}
                  </Button>
                </div>

                {/* Filter bar */}
                <div className="px-4 py-3 border-b border-[#E2E4E0] flex flex-wrap items-center gap-2">
                  <Select value={filterRole} onValueChange={setFilterRole}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[140px]" data-testid="filter-role"><SelectValue placeholder="Rolle" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('allRoles')}</SelectItem>
                      {(filterOptions.roles || []).map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={filterDept} onValueChange={setFilterDept}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[160px]" data-testid="filter-department"><SelectValue placeholder="Abteilung" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('allDepartments')}</SelectItem>
                      {(filterOptions.departments || []).map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={filterLocation} onValueChange={setFilterLocation}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[160px]" data-testid="filter-location"><SelectValue placeholder="Standort" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('allLocations')}</SelectItem>
                      {(filterOptions.locations || []).map(l => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={filterStatus} onValueChange={setFilterStatus}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[140px]" data-testid="filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('allStatuses')}</SelectItem>
                      <SelectItem value="active">{t('active')}</SelectItem>
                      <SelectItem value="inactive">{t('deactivated')}</SelectItem>
                      <SelectItem value="pending_verification">Verifizierung läuft</SelectItem>
                      <SelectItem value="locked_unverified">Gesperrt (unverifiziert)</SelectItem>
                    </SelectContent>
                  </Select>
                  {(filterRole !== 'all' || filterDept !== 'all' || filterLocation !== 'all' || filterStatus !== 'all' || search) && (
                    <Button
                      variant="ghost" size="sm"
                      onClick={() => { setFilterRole('all'); setFilterDept('all'); setFilterLocation('all'); setFilterStatus('all'); setSearch(''); }}
                      className="text-xs h-8 text-[#9CA3AF] hover:text-[#1C1F1D]"
                      data-testid="filters-clear">Zurücksetzen</Button>
                  )}
                  {/* Iter 379 — Sortier-Auswahl. „PW-Wechsel: aelteste zuerst"
                      hilft Compliance-Audits, veraltete Konten zu finden. */}
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[200px]" data-testid="filter-sort">
                      <SelectValue placeholder="Sortieren" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="created">Neueste zuerst</SelectItem>
                      <SelectItem value="name_asc">Name A–Z</SelectItem>
                      <SelectItem value="last_seen_desc">Zuletzt aktiv</SelectItem>
                      <SelectItem value="pw_oldest">PW-Wechsel: aelteste zuerst</SelectItem>
                      <SelectItem value="pw_newest">PW-Wechsel: neueste zuerst</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="ml-auto text-xs text-[#9CA3AF]" data-testid="user-count-info">
                    {total.toLocaleString('de-DE')} Nutzer · Seite {page}/{pages}
                  </div>
                </div>

                <div className="divide-y divide-[#E2E4E0]">
                  {loading ? (
                    <div className="text-center py-8 text-[#9CA3AF]">Loading...</div>
                  ) : filtered.map(u => (
                    <AdminUserRow
                      key={u.user_id}
                      user={u}
                      groups={getUserGroups(u.user_id)}
                      isCurrentUser={u.user_id === currentUser?.user_id}
                      roleColors={roleColors}
                      onToggleStatus={handleToggleStatus}
                      onEdit={setEditUser}
                      onForceLogout={handleForceLogoutUser}
                      onDelete={setDeleteConfirm}
                      autoLockHours={autoLockHours}
                    />
                  ))}
                </div>

                {/* Pagination */}
                {pages > 1 && (
                  <div className="p-4 border-t border-[#E2E4E0] flex items-center justify-between gap-2" data-testid="users-pagination">
                    <Button
                      variant="outline" size="sm" disabled={page <= 1 || loading}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      className="rounded-full border-[#E2E4E0] text-xs"
                      data-testid="pagination-prev"
                    >« Zurück</Button>
                    <div className="flex items-center gap-1.5 overflow-x-auto max-w-full">
                      {(() => {
                        // Build a compact page list: 1, …, p-1, p, p+1, …, last
                        const windowSize = 2;
                        const nums = new Set([1, pages, page]);
                        for (let i = Math.max(1, page - windowSize); i <= Math.min(pages, page + windowSize); i++) nums.add(i);
                        const sorted = Array.from(nums).sort((a, b) => a - b);
                        const out = [];
                        for (let i = 0; i < sorted.length; i++) {
                          if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push('gap' + i);
                          out.push(sorted[i]);
                        }
                        return out.map((n, i) => typeof n === 'string'
                          ? <span key={n} className="text-xs text-[#9CA3AF] px-1">…</span>
                          : (
                            <button key={n} onClick={() => setPage(n)} disabled={n === page}
                              className={`min-w-[28px] h-7 px-2 rounded-lg text-xs ${n === page ? 'bg-[#4A5D4E] text-white font-medium' : 'text-[#6B7280] hover:bg-[#F3F4F1]'}`}
                              data-testid={`pagination-page-${n}`}>{n}</button>
                          ));
                      })()}
                    </div>
                    <Button
                      variant="outline" size="sm" disabled={page >= pages || loading}
                      onClick={() => setPage(p => Math.min(pages, p + 1))}
                      className="rounded-full border-[#E2E4E0] text-xs"
                      data-testid="pagination-next"
                    >{t('next')}</Button>
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="groups">
              <div className="mb-4 p-3 bg-[#4A5D4E]/5 border border-[#4A5D4E]/20 rounded-xl flex items-start gap-2" data-testid="groups-info-box">
                <Building2 className="w-4 h-4 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
                <div className="text-[11px] text-[#4B5563] leading-relaxed">
                  <strong className="text-[#1C1F1D]">Gruppen = WER</strong> (Zielgruppen wie Stationen, Abteilungen, Teams).
                  Sie steuern die <em>Sichtbarkeit</em> von News, Umfragen, Meetings – also an wen etwas ausgespielt wird.
                  <span className="ml-1 text-[#9CA3AF]">Für Berechtigungen (<em>WAS darf jemand tun?</em>) siehe Tab „{t('rolesAndRights')}".</span>
                </div>
              </div>
              <GroupsPanel users={allUsers.length ? allUsers : users} />
            </TabsContent>

            <TabsContent value="branding">
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
                <BrandingSettings />
              </div>
            </TabsContent>

            <TabsContent value="integrations">
              <div className="space-y-6">
                <ApiConfigPanel />
                <LiveKitConfigPanel />
                <BrandingPanel />
                <EmailConfigPanel />
              </div>
            </TabsContent>

            <TabsContent value="sso">
              <SsoConfigPanel />
            </TabsContent>

            <TabsContent value="policies">
              <PoliciesPanel />
            </TabsContent>

            <TabsContent value="reminders">
              <ReminderConfigPanel />
            </TabsContent>

            <TabsContent value="resources-admin">
              <ResourcesAdminPanel />
            </TabsContent>

            <TabsContent value="roles-caps">
              <div className="mb-4 p-3 bg-[#4A5D4E]/5 border border-[#4A5D4E]/20 rounded-xl flex items-start gap-2" data-testid="roles-info-box">
                <KeyRound className="w-4 h-4 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
                <div className="text-[11px] text-[#4B5563] leading-relaxed">
                  <strong className="text-[#1C1F1D]">Rollen & Rechte = WAS</strong> (Berechtigungen wie „News veröffentlichen",
                  „Meetings moderieren", „Admin-Panel öffnen"). Jeder Nutzer hat <em>eine Rolle</em> (z. B. Admin, Moderator, Member)
                  und die Rolle definiert die konkreten Aktionen. <span className="text-[#9CA3AF]">Für Zielgruppen (<em>an WEN wird es geschickt?</em>) siehe Tab „{t('groups')}".</span>
                </div>
              </div>
              <RolesCapsPanel />
            </TabsContent>

            <TabsContent value="presets">
              <PresetEditorPanel />
            </TabsContent>

            <TabsContent value="auto-rules">
              <AutoAssignRulesPanel />
            </TabsContent>

            <TabsContent value="news-moderation">
              {/* Iter 396 — News-Moderation jetzt unter Auswertungen */}
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center" data-testid="news-moderation-moved-notice">
                <Flag className="w-10 h-10 text-[#9CA3AF] mx-auto mb-3" />
                <p className="text-sm text-[#1C1F1D] font-medium mb-1">News-Moderation ist umgezogen</p>
                <p className="text-xs text-[#6B7280] mb-4">Du findest sie jetzt unter <strong>Auswertungen</strong>.</p>
                <a href="/analytics?tab=news-moderation" className="inline-flex items-center gap-1 text-xs font-medium text-[#4A5D4E] hover:underline">Zur News-Moderation &rarr;</a>
              </div>
            </TabsContent>

            <TabsContent value="quick-scans">
              <QuickScansPanel />
            </TabsContent>

            <TabsContent value="audit-log">
              <AuditLogPanel />
            </TabsContent>

            <TabsContent value="system-audit">
              <SystemAuditPanel />
            </TabsContent>

            <TabsContent value="drivers-licenses">
              {/* Iter 396 — Führerscheine jetzt unter Auswertungen */}
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center" data-testid="drivers-licenses-moved-notice">
                <Car className="w-10 h-10 text-[#9CA3AF] mx-auto mb-3" />
                <p className="text-sm text-[#1C1F1D] font-medium mb-1">Führerscheine sind umgezogen</p>
                <p className="text-xs text-[#6B7280] mb-4">Du findest sie jetzt unter <strong>Auswertungen</strong>.</p>
                <a href="/analytics?tab=drivers-licenses" className="inline-flex items-center gap-1 text-xs font-medium text-[#4A5D4E] hover:underline">Zu den Führerscheinen &rarr;</a>
              </div>
            </TabsContent>

            <TabsContent value="invoice-config">
              <InvoiceConfigPanel />
            </TabsContent>

            <TabsContent value="filetransfer-storage" data-testid="tab-content-filetransfer-storage">
              <FiletransferStorageSettings />
            </TabsContent>
          </Tabs>
        </div>
      </main>

      {/* Edit User Dialog (extracted iter 216) */}
      <EditUserDialog user={editUser} onClose={() => setEditUser(null)} onSave={handleUpdateRole} />

      {/* Delete Confirm Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-[360px]">
          <DialogHeader><DialogTitle className="text-base font-medium">{t('confirmDelete')}</DialogTitle></DialogHeader>
          <p className="text-sm text-[#4B5563]">{deleteConfirm?.name} ({deleteConfirm?.email}) wirklich löschen?</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
            <Button onClick={handleDelete} data-testid="confirm-delete-user"
              className="bg-[#C87967] hover:bg-[#B56555] text-white rounded-full">{t('deleteUser')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite User Dialog (extracted iter 216) */}
      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={(open) => { setInviteOpen(open); if (!open) setInviteResult(null); }}
        form={inviteForm}
        onFormChange={setInviteForm}
        result={inviteResult}
        onInvite={handleInvite}
      />

      <BulkInviteDialog open={bulkInviteOpen} onClose={() => setBulkInviteOpen(false)} />
      <BulkUserImportDialog
        open={bulkImportOpen}
        onOpenChange={setBulkImportOpen}
        onImported={() => {
          qc.invalidateQueries({ queryKey: ['admin', 'users'] });
          qc.invalidateQueries({ queryKey: ['admin', 'users-all'] });
          qc.invalidateQueries({ queryKey: ['admin', 'user-filters'] });
          qc.invalidateQueries({ queryKey: ['admin', 'stats'] });
        }}
      />
    </div>
  );
}
