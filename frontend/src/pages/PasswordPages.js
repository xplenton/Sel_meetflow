import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Video, Mail, Lock, ArrowLeft, Check } from 'lucide-react';
import api from '../lib/api';

export function ForgotPasswordPage() {
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email });
      setSent(true);
    } catch {} finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#F9F9F8' }}>
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex items-center gap-2 mb-8">
          <Video className="w-7 h-7 text-[#4A5D4E]" />
          <span className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
        </div>
        <h2 className="text-2xl font-medium tracking-tight mb-2" style={{ fontFamily: 'Manrope' }}>{t('resetPassword')}</h2>
        {sent ? (
          <div className="mt-4">
            <div className="flex items-center gap-2 text-[#6B8E23] mb-4"><Check className="w-5 h-5" /><span className="text-sm">{t('passwordResetSent')}</span></div>
            <Link to="/login" className="text-[#4A5D4E] text-sm hover:underline flex items-center gap-1" data-testid="back-to-login-link"><ArrowLeft className="w-4 h-4" />{t('backToLogin')}</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 mt-6">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">{t('email')}</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="forgot-email-input" type="email" value={email} onChange={e => setEmail(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl h-11" required />
              </div>
            </div>
            <Button data-testid="forgot-submit-button" type="submit" disabled={loading}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11">{loading ? '...' : t('resetPasswordBtn')}</Button>
            <Link to="/login" className="text-[#4A5D4E] text-sm hover:underline flex items-center gap-1 justify-center" data-testid="back-to-login"><ArrowLeft className="w-4 h-4" />{t('backToLogin')}</Link>
          </form>
        )}
      </div>
    </div>
  );
}

export function ResetPasswordPage() {
  const { t } = useLanguage();
  const [params] = useSearchParams();
  const [password, setPassword] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const token = params.get('token');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await api.post('/auth/reset-password', { token, password });
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8" style={{ background: '#F9F9F8' }}>
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex items-center gap-2 mb-8">
          <Video className="w-7 h-7 text-[#4A5D4E]" />
          <span className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
        </div>
        <h2 className="text-2xl font-medium tracking-tight mb-2" style={{ fontFamily: 'Manrope' }}>{t('resetPassword')}</h2>
        {done ? (
          <div className="mt-4">
            <div className="flex items-center gap-2 text-[#6B8E23] mb-4"><Check className="w-5 h-5" /><span>Password reset successful!</span></div>
            <Link to="/login" className="text-[#4A5D4E] text-sm hover:underline" data-testid="go-to-login">{t('backToLogin')}</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 mt-6">
            {error && <div className="bg-[#C87967]/10 text-[#C87967] text-sm p-3 rounded-lg" data-testid="reset-error">{error}</div>}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">{t('enterNewPassword')}</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="reset-password-input" type="password" value={password} onChange={e => setPassword(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl h-11" required minLength={6} />
              </div>
            </div>
            <Button data-testid="reset-submit-button" type="submit" disabled={loading}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11">{loading ? '...' : t('resetPasswordBtn')}</Button>
          </form>
        )}
      </div>
    </div>
  );
}
