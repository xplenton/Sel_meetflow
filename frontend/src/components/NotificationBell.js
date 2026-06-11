import { useState, useMemo } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { useNavigate } from 'react-router-dom';
import {
  Bell, Mail, Clock, MessageSquare, Newspaper, CheckSquare, Calendar,
  CalendarCheck2, BarChart3, Send, Settings as SettingsIcon,
} from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { ScrollArea } from '../components/ui/scroll-area';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';
import { CACHE_KEYS, getCache, setCache } from '../lib/cache';

/**
 * Iter 256 — Notification-Dropdown (30 Tage, Filter, Zeit-Gruppen).
 * Iter 263 — Erweitert zum vollwertigen Notification Center:
 *  - Kategorie-Tabs (Alle / Chat / News / Aufgaben / Meetings / Buchungen / Umfragen / System)
 *  - Server-side Filter via /api/notifications?category=X
 *  - Per-Kategorie Unread-Badges via /api/notifications/categories
 *  - Deep-Link-Routing: Backend liefert `link_target`, Klick → richtige Seite
 *  - Category-Icons + Farben
 */
const NOTIFS_KEY = (filter, category) => ['notifications', filter, category, 30];
const UNREAD_KEY = ['notifications', 'unread-count'];
const CATEGORIES_KEY = ['notifications', 'categories'];

// Iter 378/380 — localStorage-Cache, damit Bell-Badge + Kategorie-Zaehler sofort
// beim Mount in korrekter Höhe erscheinen statt erst nach dem ersten
// 300-500ms Request. TanStack-Query's in-memory cache überlebt keine Page-
// Reloads — wir hydraten daher initial aus localStorage und schreiben bei
// jedem erfolgreichen Fetch zurück. (Iter 380: zentralisiert in lib/cache.js)
const NOTIF_CACHE_TTL_MS = 10 * 60 * 1000;
const loadNotifCache = (key) => {
  const v = getCache(key, { ttlMs: NOTIF_CACHE_TTL_MS });
  return v == null ? undefined : v;
};
const persistNotifCache = (key, value) => setCache(key, value);

const CATEGORY_META = {
  all:      { icon: Bell,           label: { de: 'Alle',      en: 'All' },       color: 'bg-[#E8EAE6] text-[#4A5D4E]' },
  chat:     { icon: MessageSquare,  label: { de: 'Chat',      en: 'Chat' },      color: 'bg-blue-50 text-blue-700' },
  news:     { icon: Newspaper,      label: { de: 'News',      en: 'News' },      color: 'bg-amber-50 text-amber-700' },
  tasks:    { icon: CheckSquare,    label: { de: 'Aufgaben',  en: 'Tasks' },     color: 'bg-purple-50 text-purple-700' },
  meetings: { icon: Calendar,       label: { de: 'Meetings',  en: 'Meetings' },  color: 'bg-rose-50 text-rose-700' },
  bookings: { icon: CalendarCheck2, label: { de: 'Buchungen', en: 'Bookings' },  color: 'bg-emerald-50 text-emerald-700' },
  surveys:  { icon: BarChart3,      label: { de: 'Umfragen',  en: 'Surveys' },   color: 'bg-cyan-50 text-cyan-700' },
  filetransfer: { icon: Send,       label: { de: 'Filetransfer', en: 'Filetransfer' }, color: 'bg-teal-50 text-teal-700' },
  system:   { icon: SettingsIcon,   label: { de: 'System',    en: 'System' },    color: 'bg-zinc-100 text-zinc-700' },
};

const CATEGORY_ORDER = ['all', 'chat', 'news', 'tasks', 'meetings', 'bookings', 'surveys', 'filetransfer', 'system'];

export default function NotificationBell() {
  const { t, language } = useLanguage();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('all');         // 'all' | 'unread'
  const [category, setCategory] = useState('all');     // 'all' | one of CATEGORY_ORDER[1..]
  const qc = useQueryClient();

  const { data: notifications = [] } = useQuery({
    queryKey: NOTIFS_KEY(filter, category),
    queryFn: async () => (await api.get('/notifications', {
      params: {
        since_days: 30,
        only_unread: filter === 'unread',
        category: category === 'all' ? '' : category,
        limit: 100,
      },
    })).data,
    refetchInterval: 15_000,
  });
  const { data: unreadCount = 0 } = useQuery({
    queryKey: UNREAD_KEY,
    queryFn: async () => {
      const c = (await api.get('/notifications/unread-count')).data.count;
      persistNotifCache(CACHE_KEYS.NOTIF_UNREAD, c);
      return c;
    },
    refetchInterval: 15_000,
    initialData: loadNotifCache(CACHE_KEYS.NOTIF_UNREAD),
  });
  const { data: categoryCounts = {} } = useQuery({
    queryKey: CATEGORIES_KEY,
    queryFn: async () => {
      const d = (await api.get('/notifications/categories')).data;
      persistNotifCache(CACHE_KEYS.NOTIF_CATEGORIES, d);
      return d;
    },
    refetchInterval: 15_000,
    initialData: loadNotifCache(CACHE_KEYS.NOTIF_CATEGORIES),
  });

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['notifications'] });
  };

  const markReadMutation = useMutation({
    mutationFn: async (id) => api.put(`/notifications/${id}/read`),
    onSuccess: invalidateAll,
  });
  const markAllReadMutation = useMutation({
    mutationFn: async () => api.put('/notifications/read-all'),
    onSuccess: invalidateAll,
  });

  const handleClick = (notif) => {
    if (!notif.read) markReadMutation.mutate(notif.notification_id);
    // Iter 263 — bevorzuge server-resolved link_target; Fallbacks für Legacy.
    const target = notif.link_target || notif.link
      || (notif.meeting_id ? `/meetings/${notif.meeting_id}/join` : null)
      || (notif.survey_id ? `/surveys/${notif.survey_id}` : null)
      || (notif.post_id ? `/news?post=${notif.post_id}` : null)
      || (notif.type === 'feedback_reply' ? '/profile#my-feedback' : null);
    if (target) navigate(target);
    setOpen(false);
  };

  // Group notifications by time-bucket
  const groups = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now); startOfToday.setHours(0, 0, 0, 0);
    const startOfYesterday = new Date(startOfToday); startOfYesterday.setDate(startOfYesterday.getDate() - 1);
    const startOfWeek = new Date(startOfToday); startOfWeek.setDate(startOfWeek.getDate() - 7);
    const out = { today: [], yesterday: [], week: [], older: [] };
    for (const n of notifications) {
      const d = new Date(n.created_at);
      if (d >= startOfToday) out.today.push(n);
      else if (d >= startOfYesterday) out.yesterday.push(n);
      else if (d >= startOfWeek) out.week.push(n);
      else out.older.push(n);
    }
    return out;
  }, [notifications]);

  const formatTime = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = Math.floor((now - d) / 60000);
    if (diff < 1) return 'now';
    if (diff < 60) return `${diff}m`;
    if (diff < 1440) return `${Math.floor(diff / 60)}h`;
    return `${Math.floor(diff / 1440)}d`;
  };

  const renderGroup = (label, items, testid) => {
    if (!items.length) return null;
    return (
      <div key={testid} data-testid={testid}>
        <div className="px-3 py-1.5 text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] bg-[#FAFBF9] border-b border-[#E2E4E0]">
          {label} ({items.length})
        </div>
        {items.map(n => {
          const cat = n.category || 'system';
          const meta = CATEGORY_META[cat] || CATEGORY_META.system;
          const Icon = meta.icon;
          return (
            <button key={n.notification_id} onClick={() => handleClick(n)}
              className={`w-full text-left p-3 border-b border-[#E2E4E0] hover:bg-[#F3F4F1] transition-colors ${!n.read ? 'bg-[#4A5D4E]/[0.03]' : ''}`}
              data-testid={`notification-${n.notification_id}`}>
              <div className="flex items-start gap-2.5">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${meta.color}`}>
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-[#1C1F1D] truncate">{n.title}</span>
                    {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-[#4A5D4E] flex-shrink-0" />}
                  </div>
                  <p className="text-[10px] text-[#9CA3AF] line-clamp-2 mt-0.5">{n.body}</p>
                  <span className="text-[9px] text-[#9CA3AF] mt-1 block">{formatTime(n.created_at)}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="relative w-9 h-9 rounded-full bg-white border border-[#E2E4E0] shadow-sm flex items-center justify-center hover:bg-[#F3F4F1] transition-colors active:scale-95"
          aria-label={t('notifications')}
          data-testid="notification-bell"
        >
          <Bell className="w-4 h-4 text-[#4B5563]" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-[#E25C5C] text-white text-[9px] font-bold rounded-full flex items-center justify-center ring-2 ring-white"
              data-testid="unread-count">{unreadCount > 99 ? '99+' : unreadCount}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent side="bottom" align="end" sideOffset={8} className="w-[24rem] max-w-[calc(100vw-1.5rem)] p-0" data-testid="notification-dropdown">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#E2E4E0]">
          <span className="text-sm font-medium text-[#1C1F1D]">{t('notifications')}</span>
          {unreadCount > 0 && (
            <button onClick={() => markAllReadMutation.mutate()} className="text-[10px] text-[#4A5D4E] hover:underline" data-testid="mark-all-read">{t('markAllRead')}</button>
          )}
        </div>

        {/* Iter 263 — Category tabs (horizontal scroll) */}
        <div className="flex overflow-x-auto border-b border-[#E2E4E0] text-[10px] bg-[#FAFBF9] scrollbar-thin"
             data-testid="notif-category-tabs">
          {CATEGORY_ORDER.map(cat => {
            const meta = CATEGORY_META[cat];
            const Icon = meta.icon;
            const count = Number(categoryCounts[cat] || 0);
            const active = category === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`shrink-0 inline-flex items-center gap-1 px-2.5 py-2 transition-colors ${
                  active ? 'border-b-2 border-[#4A5D4E] text-[#1C1F1D] font-medium bg-[#4A5D4E]/5' : 'text-[#6B7280] hover:bg-[#F3F4F1]'
                }`}
                data-testid={`notif-cat-${cat}`}
                title={meta.label[language] || meta.label.de}
              >
                <Icon className="w-3 h-3" />
                <span>{meta.label[language] || meta.label.de}</span>
                {count > 0 && (
                  <span className="bg-[#E25C5C] text-white rounded-full text-[8px] px-1.5 py-px font-bold"
                        data-testid={`notif-cat-count-${cat}`}>
                    {count > 99 ? '99+' : count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Filter tabs (Alle / Ungelesen) */}
        <div className="flex border-b border-[#E2E4E0] text-[11px]" data-testid="notif-filter-tabs">
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`flex-1 py-2 transition-colors ${filter === 'all' ? 'bg-[#4A5D4E]/5 border-b-2 border-[#4A5D4E] text-[#1C1F1D] font-medium' : 'text-[#6B7280] hover:bg-[#F3F4F1]'}`}
            data-testid="notif-filter-all">
            {language === 'de' ? 'Alle' : 'All'}
          </button>
          <button
            type="button"
            onClick={() => setFilter('unread')}
            className={`flex-1 py-2 transition-colors ${filter === 'unread' ? 'bg-[#4A5D4E]/5 border-b-2 border-[#4A5D4E] text-[#1C1F1D] font-medium' : 'text-[#6B7280] hover:bg-[#F3F4F1]'}`}
            data-testid="notif-filter-unread">
            {language === 'de' ? 'Ungelesen' : 'Unread'} {unreadCount > 0 && <span className="ml-1 text-[#E25C5C]">({unreadCount})</span>}
          </button>
        </div>

        <ScrollArea className="max-h-96">
          {notifications.length === 0 ? (
            <div className="text-center py-8" data-testid="notifs-empty">
              <Bell className="w-8 h-8 text-[#E2E4E0] mx-auto mb-2" />
              <p className="text-xs text-[#9CA3AF]">
                {filter === 'unread' ? (language === 'de' ? 'Keine ungelesenen Benachrichtigungen' : 'No unread notifications') : t('noNotifications')}
              </p>
            </div>
          ) : (
            <>
              {renderGroup(language === 'de' ? 'Heute' : 'Today', groups.today, 'group-today')}
              {renderGroup(language === 'de' ? 'Gestern' : 'Yesterday', groups.yesterday, 'group-yesterday')}
              {renderGroup(language === 'de' ? 'Diese Woche' : 'This week', groups.week, 'group-week')}
              {renderGroup(language === 'de' ? 'Älter (30 Tage)' : 'Older (30 days)', groups.older, 'group-older')}
            </>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
