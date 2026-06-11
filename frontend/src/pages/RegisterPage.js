import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Video, Mail, Lock, User } from 'lucide-react';

function formatApiError(detail) {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(e => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function RegisterPage() {
  const { register: registerFn } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await registerFn(email, password, name);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || t('somethingWentWrong'));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex" style={{ background: '#F9F9F8' }}>
      <div className="hidden lg:flex lg:w-1/2 items-center justify-center p-12" style={{ background: 'linear-gradient(135deg, #4A5D4E 0%, #3E4E42 100%)' }}>
        <div className="text-white max-w-md animate-fade-in">
          <div className="flex items-center gap-3 mb-8">
            <Video className="w-10 h-10" />
            <span className="text-3xl font-light tracking-tight" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
          </div>
          <h1 className="text-4xl font-light tracking-tight leading-tight mb-4" style={{ fontFamily: 'Manrope' }}>
            {t('heroRegisterTitle')}
          </h1>
          <p className="text-white/70 text-base leading-relaxed">
            {t('heroRegisterDesc')}
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm animate-fade-in">
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <Video className="w-7 h-7 text-[#4A5D4E]" />
            <span className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
          </div>

          <h2 className="text-2xl font-medium tracking-tight mb-1" style={{ fontFamily: 'Manrope' }}>{t('signUp')}</h2>
          <p className="text-[#9CA3AF] text-sm mb-8">{t('createAccount')}</p>

          {error && <div className="bg-[#C87967]/10 text-[#C87967] text-sm p-3 rounded-lg mb-4" data-testid="register-error">{error}</div>}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">{t('name')}</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="register-name-input" type="text" value={name} onChange={e => setName(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] focus:ring-[#4A5D4E] rounded-xl h-11" required />
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">{t('email')}</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="register-email-input" type="email" value={email} onChange={e => setEmail(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] focus:ring-[#4A5D4E] rounded-xl h-11" required />
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">{t('password')}</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="register-password-input" type="password" value={password} onChange={e => setPassword(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] focus:ring-[#4A5D4E] rounded-xl h-11" required minLength={8} />
              </div>
              {/* Iter 379 — Policy-Hinweis */}
              <p className="text-[11px] text-[#9CA3AF] mt-1.5">
                Min. 8 Zeichen, je 1 Gross-/Kleinbuchstabe, Ziffer und Sonderzeichen.
              </p>
            </div>
            <Button data-testid="register-submit-button" type="submit" disabled={loading}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium transition-all active:scale-95">
              {loading ? '...' : t('signUp')}
            </Button>
          </form>

          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-[#E2E4E0]" /><span className="text-xs text-[#9CA3AF]">{t('or')}</span><div className="flex-1 h-px bg-[#E2E4E0]" />
          </div>

          <Button data-testid="google-register-button" onClick={handleGoogle} variant="outline"
            className="w-full rounded-full h-11 border-[#E2E4E0] hover:bg-[#F3F4F1] font-medium transition-all">
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            {t('loginWithGoogle')}
          </Button>

          <p className="text-center text-sm text-[#9CA3AF] mt-6">
            {t('haveAccount')}{' '}
            <Link to="/login" className="text-[#4A5D4E] font-medium hover:underline" data-testid="login-link">{t('signIn')}</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
