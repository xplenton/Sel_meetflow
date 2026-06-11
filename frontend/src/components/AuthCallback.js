import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function AuthCallback() {
  const { googleLogin } = useAuth();
  const navigate = useNavigate();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const hash = window.location.hash;
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate('/login', { replace: true });
      return;
    }

    const sessionId = match[1];
    (async () => {
      try {
        const user = await googleLogin(sessionId);
        navigate('/dashboard', { replace: true, state: { user } });
      } catch (err) {
        console.error('Google auth failed:', err);
        navigate('/login', { replace: true });
      }
    })();
  }, [googleLogin, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 border-2 border-[#4A5D4E] border-t-transparent rounded-full animate-spin" />
        <p className="text-[#4B5563] text-sm" data-testid="auth-callback-loading">Authenticating...</p>
      </div>
    </div>
  );
}
