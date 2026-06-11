import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import api from '../lib/api';

import { useLanguage } from '../contexts/LanguageContext';
/**
 * Landing page for the email-verification link that was sent at register
 * time (or re-sent via the banner). Reads `?token=...`, POSTs to
 * `/auth/verify-email`, renders one of three states: loading, success,
 * error. Success CTA deep-links back to /dashboard.
 */
export default function VerifyEmailPage() {
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const [state, setState] = useState('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) { setState('error'); setMessage('Kein Token in der URL'); return; }
    api.post('/auth/verify-email', { token })
      .then(() => { setState('success'); setMessage('Deine E-Mail-Adresse wurde bestätigt.'); })
      .catch((err) => {
        setState('error');
        setMessage(err.response?.data?.detail || t('verifyFailed'));
      });
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-[#F9F9F6] flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-2xl border border-[#E2E4E0] p-10 text-center" data-testid="verify-email-card">
        {state === 'loading' && (
          <>
            <Loader2 className="w-10 h-10 mx-auto text-[#6B8E23] animate-spin" />
            <h1 className="mt-6 text-xl font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
              Bestätige deine E-Mail...
            </h1>
          </>
        )}
        {state === 'success' && (
          <>
            <CheckCircle2 className="w-14 h-14 mx-auto text-[#6B8E23]" />
            <h1 className="mt-6 text-2xl font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
              {t('emailConfirmed')}
            </h1>
            <p className="mt-3 text-sm text-[#4B5563]" data-testid="verify-email-success-msg">{message}</p>
            <Link to="/dashboard" className="mt-8 inline-flex items-center justify-center px-6 py-2.5 rounded-full bg-[#4A5D4E] text-white text-sm font-medium hover:bg-[#3E4E42] transition-colors"
              data-testid="verify-email-to-dashboard">
              {t('backToDashboard')}
            </Link>
          </>
        )}
        {state === 'error' && (
          <>
            <AlertCircle className="w-14 h-14 mx-auto text-[#C87967]" />
            <h1 className="mt-6 text-2xl font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
              {t('verifyFailed')}
            </h1>
            <p className="mt-3 text-sm text-[#4B5563]" data-testid="verify-email-error-msg">{message}</p>
            <Link to="/login" className="mt-8 inline-flex items-center justify-center px-6 py-2.5 rounded-full border border-[#E2E4E0] text-[#1C1F1D] text-sm font-medium hover:bg-[#F3F4F1]">
              {t('toLogin')}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
