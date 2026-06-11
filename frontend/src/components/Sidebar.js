import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { useBranding } from '../contexts/BrandingContext';
import { useChatUnread } from '../contexts/ChatUnreadContext';
import { useState, useEffect, useRef } from 'react';
import StatusPicker from './StatusPicker';
import UserMenu from './UserMenu';
import { Workflow, LayoutDashboard, CalendarDays, Disc, Shield, BarChart3, CalendarClock, Menu, X, MessageCircle, Monitor, Newspaper, ClipboardList, CheckSquare, Building2, Send } from 'lucide-react';
import api from '../lib/api';
import { CACHE_KEYS, getCache, setCache } from '../lib/cache';

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, key: 'dashboardHome', perm: 'dashboard' },
  { path: '/news', icon: Newspaper, key: 'news', perm: 'news' },
  { path: '/surveys', icon: ClipboardList, key: 'surveys', perm: 'surveys' },
  { path: '/tasks', icon: CheckSquare, key: 'tasks', perm: 'tasks' },
  { path: '/resources', icon: Building2, key: 'resources', perm: 'resources' },
  { path: '/filetransfer', icon: Send, key: 'filetransfer', perm: 'filetransfer' },
  { path: '/meetings', icon: Monitor, key: 'dashboard', perm: 'meetings' },
  { path: '/schedule', icon: CalendarClock, key: 'scheduling', perm: 'scheduling' },
  { path: '/chat', icon: MessageCircle, key: 'chat', perm: 'chat' },
  { path: '/calendar', icon: CalendarDays, key: 'calendar', perm: 'calendar' },
  { path: '/recordings', icon: Disc, key: 'recordings', perm: 'recordings' },
];

// Iter 378/380 — localStorage-Cache für Sidebar-Berechtigungen.
// Verhindert das kurze Aufblitzen ALLER Module beim Page-Load: zuvor hat
// `hasPerm()` während des Loading-Phase `true` zurückgegeben (= alles
// anzeigen), nach Eintreffen der Permissions wurden die nicht erlaubten
// Module wieder ausgeblendet — sichtbar als Flimmern. Mit dem Cache
// rendert die Sidebar bei Folgenavigationen sofort mit der korrekten
// Auswahl, der Refetch im Hintergrund hält den Cache frisch.
// (Iter 380: zentralisiert über lib/cache.js)

// Iter 378 — Badge-Counter-Caches. Tasks-Pending- und News-Pending-Reports-
// Zähler erscheinen sofort beim Mount mit dem letzten bekannten Wert, statt
// "0 → echter Wert"-Wackelphase nach ca. 200-500ms Request-Latenz.
const COUNTER_CACHE_TTL_MS = 10 * 60 * 1000;

function loadCachedCounter(key, userId) {
  return getCache(key, { ttlMs: COUNTER_CACHE_TTL_MS, userId });
}

function persistCounter(key, userId, value) {
  setCache(key, value, { userId });
}

function loadCachedPermissions(userId) {
  // Eigenes Schema: { user_id, permissions: [...], ts } — bewusst NICHT auf
  // die generische lib/cache.js umgestellt, weil das Top-Level-Feld
  // `permissions` heißt statt `value` und ein Schema-Wechsel die noch
  // im Browser vorhandenen Caches invalidieren würde.
  try {
    const raw = localStorage.getItem(CACHE_KEYS.USER_PERMS);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.permissions)) return null;
    // Wenn die User-ID bekannt ist, muss sie matchen. Wenn der Aufrufer
    // noch keine User-ID hat (Cold-Boot: AuthContext lädt gerade), vertrauen
    // wir dem Cache temporär — sobald der User feststeht, validiert der
    // useEffect den Cache und schreibt notfalls neu.
    if (userId && parsed.user_id !== userId) return null;
    return parsed.permissions;
  } catch { /* ignore */ }
  return null;
}

export default function Sidebar() {
  const { user } = useAuth();
  const { t } = useLanguage();
  const { branding } = useBranding();
  const { total_unread: chatUnread, top: chatTopUnread, refresh: refreshChatUnread } = useChatUnread();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Hydrate-from-cache synchronously: keine Flimmer-Phase bei Reloads.
  const [permissions, setPermissions] = useState(() => loadCachedPermissions(user?.user_id));
  const [pendingReports, setPendingReports] = useState(() =>
    (loadCachedCounter(CACHE_KEYS.NEWS_REPORTS_PENDING, user?.user_id) ?? 0));
  const [tasksPending, setTasksPending] = useState(() =>
    (loadCachedCounter(CACHE_KEYS.TASKS_PENDING, user?.user_id)?.count ?? 0));
  const [tasksOverdue, setTasksOverdue] = useState(() =>
    (loadCachedCounter(CACHE_KEYS.TASKS_PENDING, user?.user_id)?.overdue ?? 0));
  const [chatPopoverOpen, setChatPopoverOpen] = useState(false);
  const popoverRef = useRef(null);

  // Close popover on outside click
  useEffect(() => {
    if (!chatPopoverOpen) return;
    const onClick = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setChatPopoverOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [chatPopoverOpen]);

  useEffect(() => {
    if (user && user.user_id) {
      // Falls der User sich gerade gewechselt hat (z.B. Re-Login als anderer
      // Account), Cache eines fremden Users ignorieren bis zum Refetch.
      const cached = loadCachedPermissions(user.user_id);
      if (cached) setPermissions(cached);
      api.get('/user/permissions').then(({ data }) => {
        setPermissions(data.permissions);
        try {
          localStorage.setItem(CACHE_KEYS.USER_PERMS, JSON.stringify({
            user_id: user.user_id,
            permissions: data.permissions,
            ts: Date.now(),
          }));
        } catch { /* localStorage voll/disabled — non-fatal */ }
      }).catch(() => {});
    }
  }, [user]);

  // Poll pending report count every 60s for reviewers (admin/redakteur/freigeber)
  useEffect(() => {
    const role = user?.role;
    if (!user?.user_id) return;
    if (!['admin', 'redakteur', 'freigeber'].includes(role)) return;
    let cancelled = false;
    const fetchCount = () => {
      api.get('/news/reports/pending-count').then(({ data }) => {
        if (!cancelled) {
          const c = data?.count || 0;
          setPendingReports(c);
          persistCounter(CACHE_KEYS.NEWS_REPORTS_PENDING, user?.user_id, c);
        }
      }).catch(() => {});
    };
    fetchCount();
    const t = setInterval(fetchCount, 60000);
    return () => { cancelled = true; clearInterval(t); };
  }, [user]);

  // Poll my-pending-task count every 60s. Like the news-reports polling above
  // (iter 192 task module), so the sidebar mirrors how News does it.
  useEffect(() => {
    if (!user?.user_id) return;
    let cancelled = false;
    const fetchCount = () => {
      api.get('/tasks/pending-count').then(({ data }) => {
        if (!cancelled) {
          const count = data?.count || 0;
          const overdue = data?.overdue || 0;
          setTasksPending(count);
          setTasksOverdue(overdue);
          persistCounter(CACHE_KEYS.TASKS_PENDING, user?.user_id, { count, overdue });
        }
      }).catch(() => {});
    };
    fetchCount();
    const t = setInterval(fetchCount, 60000);
    // Iter 336 — refresh badge on realtime task events so the sidebar
    // counter ticks in sync with the Kanban/List/Calendar views.
    const onTaskEvent = () => fetchCount();
    window.addEventListener('meetflow:task-event', onTaskEvent);
    return () => {
      cancelled = true;
      clearInterval(t);
      window.removeEventListener('meetflow:task-event', onTaskEvent);
    };
  }, [user]);

  const hasPerm = (perm) => {
    // Iter 378 — Verhalten umgekehrt: solange Permissions nicht bekannt sind,
    // wird das Modul AUSGEBLENDET (nicht "alles anzeigen"). Verhindert das
    // Aufblitzen aller Module beim ersten Login (kein Cache). Bei Folge-
    // navigation hydratet `permissions` synchron aus localStorage, sodass die
    // Sidebar direkt mit dem korrekten Satz rendert.
    if (!permissions) return false;
    if (user?.role === 'admin') return true;
    return permissions.includes(perm);
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <>
      {/* iter 313 — mobile hamburger removed. Bottom-Nav (MobileBottomNav)
          now provides primary navigation on phones; secondary modules live
          behind the "Mehr" sheet. The desktop sidebar still mounts because
          `md:hidden` keeps it visible on >=768px viewports. */}

      {/* Iter 274 — global user menu (avatar dropdown) top-right on every page */}
      <UserMenu />

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/30 z-40 md:hidden" onClick={closeMobile} data-testid="mobile-overlay" />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}
        data-testid="sidebar">
        {/* Mobile close button */}
        <button onClick={closeMobile}
          className="absolute top-4 right-4 p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF] md:hidden"
          data-testid="mobile-menu-close">
          <X className="w-5 h-5" />
        </button>

        <div className="p-6 pb-4">
          <div className="flex items-center gap-2.5">
            {branding?.logo_url ? (
              <img
                src={branding.logo_url.startsWith('/api/')
                  ? `${process.env.REACT_APP_BACKEND_URL}${branding.logo_url}`
                  : branding.logo_url}
                alt="" className="w-7 h-7 rounded object-contain"
              />
            ) : (
              <Workflow className="w-7 h-7" style={{ color: branding?.primary_color || '#4A5D4E' }} />
            )}
            <span className="text-lg font-semibold text-[#1C1F1D] tracking-tight" style={{ fontFamily: 'Manrope' }}>
              {branding?.company_name || 'MeetFlow'}
            </span>
          </div>
        </div>

        <nav className="flex-1 py-2">
          {navItems.filter(item => hasPerm(item.perm)).map(item => {
            const isChat = item.path === '/chat';
            if (isChat) {
              return (
                <div key={item.path} className="relative" ref={popoverRef}>
                  <NavLink to={item.path} data-testid={`nav-${item.key}`}
                    onClick={closeMobile}
                    className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}>
                    <item.icon className="w-5 h-5" />
                    <span className="flex-1">{t(item.key)}</span>
                    {chatUnread > 0 && (
                      <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); refreshChatUnread(); setChatPopoverOpen(v => !v); }}
                        data-testid="chat-unread-badge"
                        title={`${chatUnread} ungelesene Nachricht(en) — Schnellzugriff`}
                        className="ml-auto min-w-[20px] h-5 px-1.5 rounded-full bg-[#C87967] text-white text-[10px] font-bold flex items-center justify-center hover:bg-[#B5624F] transition-colors"
                      >
                        {chatUnread > 99 ? '99+' : chatUnread}
                      </button>
                    )}
                  </NavLink>
                  {chatPopoverOpen && chatTopUnread.length > 0 && (
                    <div
                      data-testid="chat-unread-popover"
                      className="absolute left-full top-0 ml-1 w-72 rounded-xl border border-[#E2E4E0] bg-white shadow-2xl py-2 z-50 animate-fade-in"
                      style={{ maxHeight: '70vh', overflowY: 'auto' }}
                    >
                      <div className="px-3 py-2 border-b border-[#F3F4F1] flex items-center justify-between">
                        <span className="text-xs font-semibold text-[#1C1F1D]">{t('unread')}</span>
                        <span className="text-[10px] text-[#9CA3AF]">{chatUnread} {language === 'de' ? 'neu' : 'new'}</span>
                      </div>
                      {chatTopUnread.map(c => {
                        const initial = (c.display_name || '?').trim().charAt(0).toUpperCase();
                        return (
                          <button
                            key={c.conversation_id}
                            type="button"
                            data-testid={`chat-unread-item-${c.conversation_id}`}
                            onClick={() => { setChatPopoverOpen(false); closeMobile(); navigate(`/chat?conv=${c.conversation_id}`); }}
                            className="w-full flex items-center gap-3 px-3 py-2 hover:bg-[#F3F4F1] transition-colors text-left"
                          >
                            <div className="relative w-9 h-9 rounded-full bg-gradient-to-br from-[#4A5D4E] to-[#3E4E42] flex items-center justify-center overflow-hidden flex-shrink-0">
                              {c.display_avatar ? (
                                <img src={c.display_avatar} alt="" className="w-full h-full object-cover" />
                              ) : (
                                <span className="text-white text-xs font-medium">{initial}</span>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium text-[#1C1F1D] truncate">{c.display_name || 'Chat'}</div>
                              {c.last_message_preview && (
                                <div className="text-[10px] text-[#6B7280] truncate">{c.last_message_preview}</div>
                              )}
                            </div>
                            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#C87967] text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                              {c.unread_count > 99 ? '99+' : c.unread_count}
                            </span>
                          </button>
                        );
                      })}
                      <div className="px-3 py-2 border-t border-[#F3F4F1]">
                        <button
                          type="button"
                          data-testid="chat-unread-open-all"
                          onClick={() => { setChatPopoverOpen(false); closeMobile(); navigate('/chat'); }}
                          className="w-full text-[11px] text-[#4A5D4E] hover:underline text-center"
                        >
                          {t('openAllChats')}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            }
            return (
              <NavLink key={item.path} to={item.path} data-testid={`nav-${item.key}`}
                onClick={closeMobile}
                className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}>
                <item.icon className="w-5 h-5" />
                <span className="flex-1">{t(item.key)}</span>
                {item.path === '/tasks' && tasksPending > 0 && (
                  <span
                    data-testid="sidebar-tasks-badge"
                    title={`${tasksPending} offene Aufgabe(n)${tasksOverdue ? ` · ${tasksOverdue} überfällig` : ''}`}
                    className={`ml-auto min-w-[20px] h-5 px-1.5 rounded-full text-white text-[10px] font-bold flex items-center justify-center ${tasksOverdue > 0 ? 'bg-[#C87967]' : 'bg-[#4A5D4E]'}`}
                  >
                    {tasksPending > 99 ? '99+' : tasksPending}
                  </span>
                )}
              </NavLink>
            );
          })}
          {hasPerm('admin') && user?.role === 'admin' && (
            <>
              <NavLink to={pendingReports > 0 ? "/admin?tab=news-moderation" : "/admin"} data-testid="nav-admin" onClick={closeMobile}
                className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}>
                <Shield className="w-5 h-5" />
                <span className="flex-1">{t('admin')}</span>
                {pendingReports > 0 && (
                  <span data-testid="sidebar-reports-badge"
                    title={`${pendingReports} offene Meldung(en)`}
                    className="ml-auto min-w-[20px] h-5 px-1.5 rounded-full bg-[#C87967] text-white text-[10px] font-bold flex items-center justify-center">
                    {pendingReports > 99 ? '99+' : pendingReports}
                  </span>
                )}
              </NavLink>
              <NavLink to="/analytics" data-testid="nav-analytics" onClick={closeMobile}
                className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}>
                <BarChart3 className="w-5 h-5" /><span>{t('analytics')}</span>
              </NavLink>
            </>
          )}
        </nav>

        <div className="p-4 border-t border-[#E2E4E0]">
          <StatusPicker />
        </div>
      </aside>
    </>
  );
}
