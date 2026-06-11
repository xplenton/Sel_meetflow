import { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, MessageCircle, ListChecks, Calendar, MoreHorizontal,
  Newspaper, ClipboardList, Monitor, CalendarClock, Disc, Building2, Shield, BarChart3, User, X, Send,
} from 'lucide-react';
import { useChatUnread } from '../contexts/ChatUnreadContext';
import { usePermissions } from '../lib/permissions';

/**
 * Mobile bottom navigation (iter 312 + iter 313 + iter 314 perm-filter).
 *
 * Layout pattern (up to 5 primary slots + "More" tray):
 *
 *   ┌──────────────────────────────────────────────────────┐
 *   │ Start │ Chat │ Aufgaben │ Kalender │ Mehr            │
 *   └──────────────────────────────────────────────────────┘
 *
 * iter 314 — every entry carries a `cap` and is filtered against the
 * current user's capabilities (`usePermissions().can(cap)`). Items the
 * user can't see disappear from BOTH the bottom bar AND the "Mehr" sheet,
 * so e.g. a guest never sees a teasing "Verwaltung" tile they can't open.
 *
 * If the "Mehr" sheet would end up empty (everything filtered out), we
 * hide the More tab entirely so the bar still looks tidy.
 */
const PRIMARY = [
  { key: 'dashboard', to: '/dashboard', label: 'Start',    icon: LayoutDashboard, cap: 'view:dashboard' },
  { key: 'chat',      to: '/chat',      label: 'Chat',     icon: MessageCircle,   cap: 'view:chat' },
  { key: 'tasks',     to: '/tasks',     label: 'Aufgaben', icon: ListChecks,      cap: 'view:tasks' },
  { key: 'calendar',  to: '/calendar',  label: 'Kalender', icon: Calendar,        cap: 'view:calendar' },
];

const SECONDARY = [
  { key: 'news',          to: '/news',         label: 'News',          icon: Newspaper,      cap: 'view:news' },
  { key: 'surveys',       to: '/surveys',      label: 'Umfragen',      icon: ClipboardList,  cap: 'view:surveys' },
  { key: 'meetings',      to: '/meetings',     label: 'Webkonferenz',  icon: Monitor,        cap: 'view:meetings' },
  { key: 'schedule',      to: '/schedule',     label: 'Terminplanung', icon: CalendarClock,  cap: 'view:scheduling' },
  { key: 'recordings',    to: '/recordings',   label: 'Aufnahmen',     icon: Disc,           cap: 'view:recordings' },
  { key: 'resources',     to: '/resources',    label: 'Ressourcen',    icon: Building2,      cap: 'view:resources' },
  { key: 'filetransfer',  to: '/filetransfer', label: 'Filetransfer',  icon: Send,           cap: 'view:filetransfer' },
  { key: 'admin',         to: '/admin',        label: 'Verwaltung',    icon: Shield,         cap: 'view:admin' },
  { key: 'analytics',     to: '/analytics',    label: 'Auswertungen',  icon: BarChart3,      cap: 'view:analytics' },
  // Profile has no visibility-cap — every authenticated user can edit
  // their own profile. We always show it as the last "Mehr" item.
  { key: 'profile',       to: '/profile',      label: 'Profil',        icon: User,           cap: null },
];

function MoreSheet({ open, onClose, navigate, items }) {
  if (!open) return null;
  const go = (to) => { onClose(); navigate(to); };
  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/40 md:hidden"
        onClick={onClose}
        data-testid="mobile-more-overlay"
      />
      <div
        className="fixed bottom-0 left-0 right-0 z-50 bg-white rounded-t-2xl shadow-2xl md:hidden animate-in slide-in-from-bottom-4 duration-200"
        style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}
        data-testid="mobile-more-sheet"
      >
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <div className="text-xs uppercase tracking-wider font-semibold text-[#6B7280]">Weitere Module</div>
          <button
            onClick={onClose}
            data-testid="mobile-more-close"
            aria-label="Schließen"
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-[#F3F4F1] text-[#6B7280]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-3 gap-1 px-3 pb-3">
          {items.map(({ key, to, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => go(to)}
              data-testid={`mobile-more-${key}`}
              className="flex flex-col items-center gap-1.5 p-3 rounded-xl hover:bg-[#F3F4F1] active:scale-[0.97] transition-all"
            >
              <div className="w-10 h-10 rounded-lg bg-[#4A5D4E]/8 flex items-center justify-center">
                <Icon className="w-5 h-5 text-[#4A5D4E]" />
              </div>
              <span className="text-[11px] text-center text-[#1C1F1D] truncate max-w-full">{label}</span>
            </button>
          ))}
        </div>
        <div className="h-1 w-12 bg-[#E2E4E0] rounded-full mx-auto" />
      </div>
    </>
  );
}

export default function MobileBottomNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const { total_unread } = useChatUnread() || { total_unread: 0 };
  const perms = usePermissions();
  const can = perms?.can || (() => true);
  const loading = perms?.loading;
  const [moreOpen, setMoreOpen] = useState(false);

  // Hide on full-screen routes
  const path = location.pathname;
  if (path.startsWith('/meetings/') && path.includes('/join')) return null;
  if (path.startsWith('/live/')) return null;
  if (path.startsWith('/book/') || path.startsWith('/poll/')) return null;

  // While the permission set is still loading, render an empty placeholder
  // bar to avoid the layout shift of items suddenly appearing.
  const primaryVisible = loading ? [] : PRIMARY.filter(i => !i.cap || can(i.cap));
  const secondaryVisible = loading ? [] : SECONDARY.filter(i => !i.cap || can(i.cap));

  const isMoreActive = secondaryVisible.some(s => path.startsWith(s.to));
  const showMore = secondaryVisible.length > 0;

  return (
    <>
      <nav
        data-testid="mobile-bottom-nav"
        aria-label="Hauptnavigation"
        className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-sm border-t border-[#E2E4E0] md:hidden"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <ul
          className="grid h-14"
          style={{ gridTemplateColumns: `repeat(${primaryVisible.length + (showMore ? 1 : 0)}, minmax(0, 1fr))` }}
        >
          {primaryVisible.map(({ key, to, label, icon: Icon }) => (
            <li key={key} className="flex">
              <NavLink
                to={to}
                data-testid={`mobile-nav-${key}`}
                className={({ isActive }) =>
                  `flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium relative transition-colors ${
                    isActive
                      ? 'text-[#4A5D4E]'
                      : 'text-[#9CA3AF] hover:text-[#4A5D4E]'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <div className="relative">
                      <Icon className="w-5 h-5" />
                      {key === 'chat' && total_unread > 0 && (
                        <span
                          className="absolute -top-1 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-[#C87967] text-white text-[9px] font-bold flex items-center justify-center"
                          data-testid="mobile-nav-chat-badge"
                        >
                          {total_unread > 99 ? '99+' : total_unread}
                        </span>
                      )}
                    </div>
                    <span className="truncate max-w-full px-1">{label}</span>
                    {isActive && (
                      <span className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-[#4A5D4E]" />
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
          {showMore && (
            <li className="flex">
              <button
                onClick={() => setMoreOpen(true)}
                data-testid="mobile-nav-more"
                className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium relative transition-colors ${
                  isMoreActive
                    ? 'text-[#4A5D4E]'
                    : 'text-[#9CA3AF] hover:text-[#4A5D4E]'
                }`}
              >
                <MoreHorizontal className="w-5 h-5" />
                <span className="truncate max-w-full px-1">Mehr</span>
                {isMoreActive && (
                  <span className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full bg-[#4A5D4E]" />
                )}
              </button>
            </li>
          )}
        </ul>
      </nav>
      <MoreSheet
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        navigate={navigate}
        items={secondaryVisible}
      />
    </>
  );
}
