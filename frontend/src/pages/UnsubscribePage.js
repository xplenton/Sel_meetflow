import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { MailOpen, MailCheck, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

import { useLanguage } from '../contexts/LanguageContext';
const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function UnsubscribePage() {
  const { t } = useLanguage();
  const { token } = useParams();
  const [state, setState] = useState('loading'); // loading | ready | done_unsub | done_resub | error
  const [user, setUser] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API_URL}/api/unsubscribe/${token}`);
        setUser(data);
        setState('ready');
      } catch (err) {
        setErrorMsg(err.response?.data?.detail || 'Ungültiger oder abgelaufener Link');
        setState('error');
      }
    })();
  }, [token]);

  const handleUnsubscribe = async () => {
    setSubmitting(true);
    try {
      await axios.post(`${API_URL}/api/unsubscribe/${token}`);
      setState('done_unsub');
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Fehler beim Abmelden');
      setState('error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleResubscribe = async () => {
    setSubmitting(true);
    try {
      await axios.post(`${API_URL}/api/unsubscribe/${token}/resubscribe`);
      setState('done_resub');
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Fehler beim Reaktivieren');
      setState('error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9F9F8] flex items-center justify-center p-4" data-testid="unsubscribe-page">
      <div className="w-full max-w-md bg-white border border-[#E2E4E0] rounded-2xl p-8 shadow-sm">
        <div className="flex items-center justify-center w-14 h-14 rounded-full bg-[#4A5D4E]/10 mx-auto mb-5">
          <MailOpen className="w-6 h-6 text-[#4A5D4E]" />
        </div>

        <h1 className="text-2xl font-medium tracking-tight text-center mb-2" style={{ fontFamily: 'Manrope' }}>
          {t('newsletterUnsubscribe')}
        </h1>

        {state === 'loading' && (
          <div className="py-8 flex flex-col items-center gap-3 text-[#6B7280]" data-testid="unsubscribe-loading">
            <Loader2 className="w-5 h-5 animate-spin" />
            <p className="text-sm">Lade Abmelde-Informationen...</p>
          </div>
        )}

        {state === 'error' && (
          <div className="py-6 text-center space-y-3" data-testid="unsubscribe-error">
            <AlertCircle className="w-10 h-10 text-[#B5524B] mx-auto" />
            <p className="text-sm text-[#1C1F1D]">{errorMsg}</p>
            <p className="text-xs text-[#9CA3AF]">
              Bitte melde Dich in Deinem Konto an und verwalte Deine E-Mail-Einstellungen im Profil.
            </p>
            <Link to="/login" className="inline-block">
              <Button variant="outline" className="rounded-full mt-2" data-testid="unsubscribe-login-link">
                {t('toLogin')}
              </Button>
            </Link>
          </div>
        )}

        {state === 'ready' && user && (
          <div className="space-y-5" data-testid="unsubscribe-ready">
            <p className="text-sm text-[#4A5D4E] text-center">
              {user.newsletter_enabled
                ? 'Du bist derzeit für den Newsletter angemeldet.'
                : 'Du hast den Newsletter bereits abbestellt.'}
            </p>

            <div className="bg-[#F3F4F1] rounded-xl p-4">
              <p className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1">Konto</p>
              <p className="text-sm font-medium text-[#1C1F1D]" data-testid="unsubscribe-email">
                {user.email}
              </p>
              {user.name && <p className="text-xs text-[#9CA3AF] mt-0.5">{user.name}</p>}
            </div>

            {user.newsletter_enabled ? (
              <>
                <p className="text-xs text-[#6B7280] text-center leading-relaxed">
                  Wenn Du Dich abmeldest, erhaeltst Du keine Newsletter-E-Mails mehr zu News-Beitraegen.
                  Pflicht-Informationen (z.&nbsp;B. zu Meetings) erhaeltst Du weiterhin.
                </p>
                <Button
                  onClick={handleUnsubscribe}
                  disabled={submitting}
                  className="w-full bg-[#B5524B] hover:bg-[#9C463F] text-white rounded-full h-11 font-medium"
                  data-testid="confirm-unsubscribe-button"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Ja, Newsletter abbestellen'}
                </Button>
              </>
            ) : (
              <Button
                onClick={handleResubscribe}
                disabled={submitting}
                className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium"
                data-testid="resubscribe-button"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Newsletter wieder aktivieren'}
              </Button>
            )}
          </div>
        )}

        {state === 'done_unsub' && (
          <div className="py-6 text-center space-y-4" data-testid="unsubscribe-done">
            <CheckCircle2 className="w-10 h-10 text-[#4A5D4E] mx-auto" />
            <p className="text-sm text-[#1C1F1D]">
              {t('unsubscribeSuccess')}
            </p>
            <p className="text-xs text-[#9CA3AF]">
              Hast Du es Dir anders überlegt?
            </p>
            <Button
              onClick={handleResubscribe}
              disabled={submitting}
              variant="outline"
              className="rounded-full"
              data-testid="resubscribe-after-unsub-button"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Newsletter wieder aktivieren'}
            </Button>
          </div>
        )}

        {state === 'done_resub' && (
          <div className="py-6 text-center space-y-3" data-testid="resubscribe-done">
            <MailCheck className="w-10 h-10 text-[#4A5D4E] mx-auto" />
            <p className="text-sm text-[#1C1F1D]">
              {t('resubscribeSuccess')}
            </p>
            <Link to="/login" className="inline-block">
              <Button variant="outline" className="rounded-full mt-2" data-testid="resub-login-link">
                {t('toLogin')}
              </Button>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
