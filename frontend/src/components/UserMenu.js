import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel,
} from './ui/dropdown-menu';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from './ui/alert-dialog';
import { LogOut, ShieldOff, User, Loader2, Moon, Sun, Globe, KeyRound } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import NotificationBell from './NotificationBell';
import ChangePasswordDialog from './ChangePasswordDialog';
import { useLanguage } from '../contexts/LanguageContext';
import { useTheme } from '../contexts/ThemeContext';

export default function UserMenu() {
  const { user, logout } = useAuth();
  const { t, language, toggleLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);
  const [loggingOutAll, setLoggingOutAll] = useState(false);
  // Iter 379 — Passwort-ändern-Dialog
  const [pwDialogOpen, setPwDialogOpen] = useState(false);

  if (!user) return null;

  const initials = (user.name || user.email || '?').split(/\s+/).map(s => s[0]).slice(0, 2).join('').toUpperCase();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const handleLogoutEverywhere = async () => {
    setLoggingOutAll(true);
    // Iter 276 — set a global flag so the axios interceptor suppresses the
    // SessionExpiryBanner while we are intentionally invalidating sessions.
    window.__mf_logging_out = true;
    try {
      await api.post('/auth/logout-everywhere');
      toast.success('Alle Sitzungen wurden beendet');
      setConfirmAllOpen(false);
      // Local logout cleanup + redirect
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Fehler beim Abmelden');
    } finally {
      setLoggingOutAll(false);
      // Clear flag after a beat so any in-flight 401s have settled.
      setTimeout(() => { window.__mf_logging_out = false; }, 1500);
    }
  };

  return (
    <>
      {/* Iter 278 — Top-right cluster: NotificationBell + Avatar dropdown */}
      <div className="fixed top-3 right-3 sm:top-4 sm:right-4 z-50 flex items-center gap-2">
        <NotificationBell />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              data-testid="user-menu-trigger"
              aria-label={user.name || user.email}
              className="flex items-center gap-2 bg-white border border-[#E2E4E0] rounded-full shadow-sm pl-1 pr-3 py-1 hover:bg-[#F3F4F1] transition-colors active:scale-95"
            >
            {user.avatar && user.avatar.startsWith('/api/users/avatar/') ? (
              <img
                src={`${process.env.REACT_APP_BACKEND_URL}${user.avatar}`}
                alt=""
                className="w-7 h-7 rounded-full object-cover"
              />
            ) : user.avatar ? (
              <img src={user.avatar} alt="" className="w-7 h-7 rounded-full object-cover" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-[#4A5D4E] text-white text-[11px] font-semibold flex items-center justify-center">
                {initials}
              </div>
            )}
            <span className="hidden sm:inline text-xs font-medium text-[#1C1F1D] max-w-[140px] truncate">
              {user.name || user.email.split('@')[0]}
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end" sideOffset={6}
          className="w-64 mt-1"
          data-testid="user-menu-content"
        >
          <DropdownMenuLabel className="pb-1">
            <div className="font-medium text-[#1C1F1D] truncate">{user.name || user.email.split('@')[0]}</div>
            <div className="text-[11px] text-[#9CA3AF] font-normal truncate">{user.email}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            data-testid="user-menu-profile"
            onClick={() => navigate('/profile')}
            className="cursor-pointer"
          >
            <User className="w-4 h-4 mr-2 text-[#4A5D4E]" />
            Profil
          </DropdownMenuItem>
          {/* Iter 379 — Passwort ändern */}
          <DropdownMenuItem
            data-testid="user-menu-change-password"
            onSelect={(e) => { e.preventDefault(); setTimeout(() => setPwDialogOpen(true), 80); }}
            className="cursor-pointer"
          >
            <KeyRound className="w-4 h-4 mr-2 text-[#4A5D4E]" />
            Passwort ändern
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            data-testid="user-menu-theme"
            onSelect={(e) => { e.preventDefault(); toggleTheme(); }}
            className="cursor-pointer"
          >
            {theme === 'dark'
              ? <><Sun className="w-4 h-4 mr-2 text-[#D4A373]" />{t('lightMode') || 'Heller Modus'}</>
              : <><Moon className="w-4 h-4 mr-2 text-[#4A5D4E]" />{t('darkMode') || 'Dunkler Modus'}</>}
          </DropdownMenuItem>
          <DropdownMenuItem
            data-testid="user-menu-language"
            onSelect={(e) => { e.preventDefault(); toggleLanguage(); }}
            className="cursor-pointer"
          >
            <Globe className="w-4 h-4 mr-2 text-[#4A5D4E]" />
            {language === 'en' ? 'Deutsch' : 'English'}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            data-testid="user-menu-logout-everywhere"
            onSelect={(e) => {
              e.preventDefault();
              // Iter 275 — defer the dialog opening to the next tick so
              // Radix's dropdown can finish its close + focus-restore dance
              // before the AlertDialog grabs focus. Without this delay,
              // some browsers race the two portals and the dialog never
              // becomes visible.
              setTimeout(() => setConfirmAllOpen(true), 80);
            }}
            className="cursor-pointer text-[#C87967] focus:text-[#C87967] focus:bg-[#C87967]/5"
          >
            <ShieldOff className="w-4 h-4 mr-2" />
            Aus allen Geräten abmelden
          </DropdownMenuItem>
          <DropdownMenuItem
            data-testid="user-menu-logout"
            onClick={handleLogout}
            className="cursor-pointer text-[#C87967] focus:text-[#C87967] focus:bg-[#C87967]/5"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Abmelden
          </DropdownMenuItem>
        </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <AlertDialog open={confirmAllOpen} onOpenChange={setConfirmAllOpen}>
        <AlertDialogContent data-testid="logout-everywhere-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-[#C87967]">
              <ShieldOff className="w-5 h-5" />
              Aus allen Geräten abmelden?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-[13px] text-[#4B5563] leading-relaxed">
              Dadurch werden ALLE bestehenden Sitzungen sofort beendet — auf diesem Gerät,
              anderen Browsern und Smartphones. Du musst dich überall neu anmelden.
              Nützlich, wenn du dein Handy verloren hast oder dich an einem fremden Gerät
              vergessen hast.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="logout-everywhere-cancel">Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              data-testid="logout-everywhere-confirm"
              onClick={handleLogoutEverywhere}
              disabled={loggingOutAll}
              className="bg-[#C87967] hover:bg-[#B5624F] text-white"
            >
              {loggingOutAll
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />…</>
                : <>Ja, überall abmelden</>}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Iter 379 — Passwort ändern Dialog */}
      <ChangePasswordDialog open={pwDialogOpen} onClose={() => setPwDialogOpen(false)} />
    </>
  );
}
