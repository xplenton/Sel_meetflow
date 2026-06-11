import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Video, VideoOff, Mic, MicOff, Settings, ArrowRight, Clock, XCircle, Loader2, AlertTriangle } from 'lucide-react';
import api from '../lib/api';
import { resolveLiveRoute } from '../lib/liveRoute';

// Translate WebRTC / getUserMedia error codes to user-friendly German strings.
// iOS-aware: adds Safari-specific hints.
function translateMediaError(err, isIOS = false) {
  const name = err?.name || '';
  const map = {
    NotAllowedError: {
      code: 'NotAllowed',
      title: 'Zugriff verweigert',
      message: isIOS
        ? 'Bitte erlaube den Kamera- und Mikrofonzugriff. Auf dem iPhone: Einstellungen > Safari > Kamera/Mikrofon > "Fragen" oder "Erlauben" wählen. Danach diese Seite neu laden.'
        : 'Bitte erlaube den Kamera- und Mikrofonzugriff im Browser (Adressleiste -> Schloss-Symbol -> Berechtigungen).',
    },
    PermissionDeniedError: {
      code: 'NotAllowed',
      title: 'Zugriff verweigert',
      message: 'Kamera/Mikrofon-Zugriff wurde verweigert. Browser-Berechtigungen prüfen.',
    },
    NotFoundError: {
      code: 'NotFound',
      title: 'Kein Gerät gefunden',
      message: 'Es wurde kein Mikrofon oder keine Kamera gefunden. Ist ein Gerät angeschlossen?',
    },
    DevicesNotFoundError: {
      code: 'NotFound',
      title: 'Kein Gerät gefunden',
      message: 'Es wurde kein Mikrofon oder keine Kamera gefunden.',
    },
    NotReadableError: {
      code: 'NotReadable',
      title: 'Gerät wird verwendet',
      message: isIOS
        ? 'Kamera/Mikrofon ist gerade belegt. Schließe andere Apps (FaceTime, Zoom, Kamera-App) und versuche es erneut.'
        : 'Kamera/Mikrofon ist von einem anderen Programm belegt. Schließe andere Videokonferenzen und versuche es erneut.',
    },
    TrackStartError: {
      code: 'NotReadable',
      title: 'Gerät nicht bereit',
      message: 'Das Gerät ist aktuell nicht verfügbar. Bitte erneut versuchen.',
    },
    OverconstrainedError: {
      code: 'Overconstrained',
      title: 'Gerät nicht geeignet',
      message: 'Das ausgewählte Gerät unterstuetzt die Einstellungen nicht. Automatische Rueckkehr zur Standard-Kamera...',
    },
    ConstraintNotSatisfiedError: {
      code: 'Overconstrained',
      title: 'Einstellung nicht unterstuetzt',
      message: 'Das Gerät unterstuetzt die gewuenschten Einstellungen nicht.',
    },
    SecurityError: {
      code: 'Security',
      title: 'Kein sicherer Kontext',
      message: 'Kamera/Mikrofon funktionieren nur über HTTPS. Bitte die App über eine https://-URL aufrufen.',
    },
    TypeError: {
      code: 'TypeError',
      title: 'Browser nicht unterstuetzt',
      message: 'Dein Browser unterstuetzt diese Funktion nicht. Bitte Safari (iOS), Chrome oder Firefox verwenden.',
    },
  };
  return map[name] || {
    code: 'Unknown',
    title: 'Fehler beim Gerät-Zugriff',
    message: err?.message || 'Kamera/Mikrofon konnten nicht gestartet werden. Bitte erneut versuchen.',
  };
}

export default function PreJoinPage() {
  const { meetingId } = useParams();
  const { user } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const pollRef = useRef(null);

  const [meeting, setMeeting] = useState(null);
  const [cameraOn, setCameraOn] = useState(true);
  const [micOn, setMicOn] = useState(true);
  const [devices, setDevices] = useState({ video: [], audio: [] });
  const [selectedVideo, setSelectedVideo] = useState('');
  const [selectedAudio, setSelectedAudio] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [permissionError, setPermissionError] = useState(null); // {code, message}
  const [needsUserGesture, setNeedsUserGesture] = useState(false);
  const [lobbyState, setLobbyState] = useState(null); // null | 'waiting' | 'rejected'

  // Detect iOS/Safari for targeted hints
  const isIOS = useMemo(() => {
    if (typeof navigator === 'undefined') return false;
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }, []);

  const enumerateDevs = useCallback(async () => {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      const video = devs.filter(d => d.kind === 'videoinput');
      const audio = devs.filter(d => d.kind === 'audioinput');
      setDevices({ video, audio });
      if (video.length && !selectedVideo) setSelectedVideo(video[0].deviceId);
      if (audio.length && !selectedAudio) setSelectedAudio(audio[0].deviceId);
    } catch {}
  }, [selectedVideo, selectedAudio]);

  const startMedia = useCallback(async (videoDeviceId, audioDeviceId) => {
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(tr => tr.stop());
        streamRef.current = null;
      }
      if (!cameraOn && !micOn) {
        if (videoRef.current) videoRef.current.srcObject = null;
        await enumerateDevs();
        setPermissionError(null);
        return;
      }
      // iOS-friendly: use plain boolean on first request (no deviceId),
      // then fall back to plain boolean if detailed constraints fail.
      const hasBeenGrantedBefore = streamRef.current !== null;
      const constraints = {};
      if (cameraOn) {
        constraints.video = (videoDeviceId && hasBeenGrantedBefore)
          ? { deviceId: { exact: videoDeviceId } }
          : true;
      }
      if (micOn) {
        constraints.audio = (audioDeviceId && hasBeenGrantedBefore)
          ? { deviceId: { exact: audioDeviceId } }
          : true;
      }
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (err) {
        // If OverconstrainedError or NotFoundError — retry with plain booleans
        if (err && (err.name === 'OverconstrainedError' || err.name === 'NotFoundError') && (videoDeviceId || audioDeviceId)) {
          const fallback = {};
          if (cameraOn) fallback.video = true;
          if (micOn) fallback.audio = true;
          stream = await navigator.mediaDevices.getUserMedia(fallback);
        } else {
          throw err;
        }
      }
      streamRef.current = stream;
      setPermissionError(null);
      setNeedsUserGesture(false);
      if (videoRef.current) videoRef.current.srcObject = stream;
      await enumerateDevs();
    } catch (err) {
      console.error('Media error:', err?.name, err?.message);
      // Translate DOMException to user-friendly message
      const translated = translateMediaError(err, isIOS);
      setPermissionError(translated);
      // iOS needs a user gesture for retry after NotAllowedError
      if (translated.code === 'NotAllowed' || translated.code === 'NotReadable') {
        setNeedsUserGesture(true);
      }
      // Try degrading: if video+audio failed, try audio only
      if (cameraOn && micOn && translated.code !== 'NotAllowed') {
        try {
          const fallback = await navigator.mediaDevices.getUserMedia({ audio: true });
          streamRef.current = fallback;
          setCameraOn(false);
          setPermissionError({ code: 'VideoOnly', message: 'Nur Mikrofon verfügbar. Die Kamera konnte nicht gestartet werden.' });
          await enumerateDevs();
          return;
        } catch {}
      }
      await enumerateDevs();
    }
  }, [cameraOn, micOn, enumerateDevs, isIOS]);

  // Retry button — user-gesture triggered, important for iOS Safari
  const retryMedia = useCallback(async () => {
    // On Chromium/Firefox, once the user has persistently denied, a bare
    // getUserMedia() call fails instantly without re-prompting. Detect
    // that state via the Permissions API and surface it clearly so the
    // user isn't left clicking a dead button (iter 122).
    try {
      if (navigator.permissions?.query) {
        const [camPerm, micPerm] = await Promise.all([
          navigator.permissions.query({ name: 'camera' }).catch(() => null),
          navigator.permissions.query({ name: 'microphone' }).catch(() => null),
        ]);
        const camDenied = camPerm?.state === 'denied';
        const micDenied = micPerm?.state === 'denied';
        if ((cameraOn && camDenied) || (micOn && micDenied)) {
          setPermissionError({
            code: 'NotAllowed',
            title: 'Zugriff dauerhaft blockiert',
            message: isIOS
              ? 'Die Freigabe wurde dauerhaft verweigert. Oeffne Einstellungen > Safari > Kamera/Mikrofon, wähle "Fragen" oder "Erlauben" und lade diese Seite neu.'
              : 'Der Browser hat den Zugriff dauerhaft blockiert. Klicke links neben der URL auf das Schloss-Symbol und setze Kamera/Mikrofon auf "Zulassen". Danach die Seite neu laden.',
          });
          setNeedsUserGesture(false);
          return;
        }
      }
    } catch { /* best-effort permission probe */ }
    setPermissionError(null);
    setNeedsUserGesture(false);
    await startMedia(selectedVideo, selectedAudio);
  }, [startMedia, selectedVideo, selectedAudio, cameraOn, micOn, isIOS]);

  // "Ohne Kamera/Mikrofon beitreten" — ultima ratio for users whose
  // browser permission is stuck on denied. We turn off both toggles so
  // the meeting page boots without trying to capture, then the normal
  // handleJoin flow runs (iter 122).
  const joinWithoutMedia = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(tr => tr.stop());
      streamRef.current = null;
    }
    setCameraOn(false);
    setMicOn(false);
    setPermissionError(null);
    setNeedsUserGesture(false);
  }, []);

  useEffect(() => {
    startMedia(selectedVideo, selectedAudio);
    return () => { if (streamRef.current) streamRef.current.getTracks().forEach(tr => tr.stop()); };
  }, [cameraOn, micOn, selectedVideo, selectedAudio, startMedia]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/meetings/${meetingId}`);
        setMeeting(data);
      } catch { setError('Meeting nicht gefunden'); }
    })();
  }, [meetingId]);

  // Poll lobby status when waiting
  useEffect(() => {
    if (lobbyState !== 'waiting') return;
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/meetings/${meetingId}/lobby-status`);
        if (data.status === 'approved') {
          clearInterval(pollRef.current);
          if (streamRef.current) streamRef.current.getTracks().forEach(tr => tr.stop());
          // Use the backend's sticky transport decision so every lobby-
          // approved joiner lands on the same transport as the host.
          const nextRoute = await resolveLiveRoute(meeting?.meeting_id || meetingId);
          navigate(nextRoute, { state: { cameraOn, micOn, selectedVideo, selectedAudio } });
        } else if (data.status === 'rejected') {
          clearInterval(pollRef.current);
          setLobbyState('rejected');
        }
      } catch {}
    }, 2000);
    return () => clearInterval(pollRef.current);
  }, [lobbyState, meetingId, navigate, cameraOn, micOn, selectedVideo, selectedAudio, meeting]);

  /**
   * Hybrid routing (iter 139 sticky): delegates to the backend's
   * `/meetings/{id}/transport` endpoint which commits to `mesh` or
   * `livekit` on the first call and returns the same answer to every
   * subsequent participant. That guarantees all joiners of a meeting
   * end up on the same transport regardless of join order.
   */
  const chooseLiveRoute = useCallback(async () => {
    return resolveLiveRoute(meeting?.meeting_id || meetingId);
  }, [meeting, meetingId]);

  const handleJoin = async () => {
    setLoading(true);
    setError('');
    try {
      const { data: lobbyData } = await api.post(`/meetings/${meeting?.meeting_id || meetingId}/join-lobby`);
      if (lobbyData.lobby) {
        setLobbyState('waiting');
        setLoading(false);
        return;
      }
      await api.post(`/meetings/${meeting?.meeting_id || meetingId}/join`);
      if (streamRef.current) streamRef.current.getTracks().forEach(tr => tr.stop());
      const nextRoute = await chooseLiveRoute();
      navigate(nextRoute, {
        state: { cameraOn, micOn, selectedVideo, selectedAudio }
      });
    } catch (err) {
      setError('Beitritt fehlgeschlagen');
    } finally { setLoading(false); }
  };

  // Lobby waiting screen
  if (lobbyState === 'waiting') {
    return (
      <div className="min-h-screen bg-[#F9F9F8] flex items-center justify-center p-6" data-testid="lobby-waiting-page">
        <div className="w-full max-w-md text-center animate-fade-in">
          <div className="w-16 h-16 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center mx-auto mb-6">
            <Clock className="w-8 h-8 text-[#4A5D4E]" />
          </div>
          <h1 className="text-xl font-medium text-[#1C1F1D] mb-2">{t('lobbyWaiting')}</h1>
          <p className="text-sm text-[#6B7280] mb-6">
            {t('lobbyWaitingHint')}
          </p>
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-5 mb-4">
            <p className="text-sm font-medium text-[#1C1F1D]">{meeting?.title || 'Meeting'}</p>
            <div className="flex items-center justify-center gap-2 mt-3">
              <Loader2 className="w-4 h-4 animate-spin text-[#4A5D4E]" />
              <span className="text-xs text-[#9CA3AF]" data-testid="lobby-waiting-status">Warten auf Zulassung...</span>
            </div>
          </div>
          <Button variant="outline" onClick={() => { setLobbyState(null); clearInterval(pollRef.current); }}
            className="text-xs" data-testid="lobby-cancel-btn">
            {t('cancel')}
          </Button>
        </div>
      </div>
    );
  }

  // Lobby rejected screen
  if (lobbyState === 'rejected') {
    return (
      <div className="min-h-screen bg-[#F9F9F8] flex items-center justify-center p-6" data-testid="lobby-rejected-page">
        <div className="w-full max-w-md text-center animate-fade-in">
          <div className="w-16 h-16 rounded-full bg-[#C87967]/10 flex items-center justify-center mx-auto mb-6">
            <XCircle className="w-8 h-8 text-[#C87967]" />
          </div>
          <h1 className="text-xl font-medium text-[#1C1F1D] mb-2">{t('lobbyRejected')}</h1>
          <p className="text-sm text-[#6B7280] mb-6">
            {t('lobbyRejectedHint')}
          </p>
          <Button onClick={() => navigate('/dashboard')} className="bg-[#4A5D4E] text-white"
            data-testid="lobby-back-btn">
            {t('backToDashboard')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F9F8] flex items-center justify-center p-6" data-testid="pre-join-page">
      <div className="w-full max-w-4xl animate-fade-in">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
            {meeting?.title || 'Meeting'}
          </h1>
          <p className="text-[#9CA3AF] text-sm mt-1">{t('readyToJoin')}</p>
          {meeting?.lobby_enabled && (
            <p className="text-[10px] text-[#D4A373] mt-1" data-testid="lobby-enabled-badge">
              Warteraum aktiv — Host muss Sie zulassen
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
          {/* Video Preview */}
          <div className="md:col-span-8">
            <div className="video-tile aspect-video rounded-2xl overflow-hidden relative bg-[#1A1D1B]">
              {cameraOn && !permissionError ? (
                <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" style={{ transform: 'scaleX(-1)' }} />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="w-20 h-20 rounded-full bg-[#4A5D4E] flex items-center justify-center text-white text-2xl font-medium">
                    {user?.name?.[0]?.toUpperCase() || 'U'}
                  </div>
                </div>
              )}
              {/* Permission-Error Overlay (especially important for iOS) */}
              {permissionError && (
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center p-4 sm:p-6" data-testid="media-permission-error">
                  <div className="bg-white rounded-xl p-4 sm:p-6 max-w-sm text-center shadow-2xl">
                    <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-[#C87967]" />
                    <h3 className="text-sm sm:text-base font-semibold text-[#1C1F1D] mb-2">{permissionError.title}</h3>
                    <p className="text-xs sm:text-sm text-[#4B5563] mb-4 leading-relaxed">{permissionError.message}</p>
                    {isIOS && permissionError.code === 'NotAllowed' && (
                      <div className="bg-[#F3F4F1] rounded-lg p-3 text-left text-[11px] text-[#4B5563] mb-4" data-testid="ios-permission-hint">
                        <p className="font-semibold text-[#4A5D4E] mb-1">iPhone/iPad Hinweis:</p>
                        <ol className="list-decimal list-inside space-y-0.5">
                          <li>{t('iosSafariSettingsStep')}</li>
                          <li>{t('iosSafariAllowStep')}</li>
                          <li>{t('reloadThisPage')}</li>
                        </ol>
                      </div>
                    )}
                    {needsUserGesture && (
                      <Button
                        onClick={retryMedia}
                        className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-9"
                        data-testid="retry-media-btn"
                      >
                        Zugriff erneut anfragen
                      </Button>
                    )}
                    {permissionError.code === 'NotAllowed' && (
                      <Button
                        variant="outline"
                        onClick={joinWithoutMedia}
                        className="w-full mt-2 border-[#E2E4E0] rounded-full text-xs h-9"
                        data-testid="join-without-media-btn"
                      >
                        {t('joinWithoutCameraMic')}
                      </Button>
                    )}
                    {permissionError.code === 'VideoOnly' && (
                      <Button variant="outline" onClick={retryMedia}
                        className="w-full mt-2 border-[#E2E4E0] rounded-full text-xs h-9"
                        data-testid="retry-with-camera-btn">
                        Kamera erneut versuchen
                      </Button>
                    )}
                  </div>
                </div>
              )}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
                <button onClick={() => setMicOn(!micOn)} data-testid="pre-join-mic-toggle"
                  className={`p-3 rounded-full transition-all ${micOn ? 'bg-white/20 text-white hover:bg-white/30' : 'bg-[#C87967] text-white'}`}>
                  {micOn ? <Mic className="w-5 h-5" /> : <MicOff className="w-5 h-5" />}
                </button>
                <button onClick={() => setCameraOn(!cameraOn)} data-testid="pre-join-camera-toggle"
                  className={`p-3 rounded-full transition-all ${cameraOn ? 'bg-white/20 text-white hover:bg-white/30' : 'bg-[#C87967] text-white'}`}>
                  {cameraOn ? <Video className="w-5 h-5" /> : <VideoOff className="w-5 h-5" />}
                </button>
              </div>
            </div>
            {/* iOS pre-flight hint — show before permission is requested */}
            {isIOS && !permissionError && !streamRef.current && (
              <p className="text-[10px] text-[#9CA3AF] mt-2 text-center" data-testid="ios-preflight-hint">
                iOS: Beim ersten Zugriff fragt Safari nach Kamera-/Mikrofonfreigabe. Bitte „Erlauben" wählen.
              </p>
            )}
          </div>

          {/* Settings Panel */}
          <div className="md:col-span-4 space-y-5">
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-5">
              <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2 mb-4">
                <Settings className="w-4 h-4 text-[#4A5D4E]" /> {t('deviceSettings')}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="text-xs text-[#6B7280] mb-1 block">{t('camera')}</label>
                  <Select value={selectedVideo} onValueChange={setSelectedVideo}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg text-xs h-9" data-testid="camera-select">
                      <SelectValue placeholder={devices.video.length === 0 ? t('noCameraFound') : t('camera')} />
                    </SelectTrigger>
                    <SelectContent>
                      {devices.video.length === 0 && (
                        <SelectItem value="__none" disabled className="text-xs text-[#9CA3AF]">{t('noCameraFound')}</SelectItem>
                      )}
                      {devices.video.map((d, i) => (
                        <SelectItem key={d.deviceId || `cam-${i}`} value={d.deviceId || `cam-${i}`} className="text-xs">
                          {d.label || `Kamera ${i + 1}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-[#6B7280] mb-1 block">{t('microphone')}</label>
                  <Select value={selectedAudio} onValueChange={setSelectedAudio}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg text-xs h-9" data-testid="mic-select">
                      <SelectValue placeholder={devices.audio.length === 0 ? 'Kein Mikrofon gefunden' : 'Mikrofon wählen'} />
                    </SelectTrigger>
                    <SelectContent>
                      {devices.audio.length === 0 && (
                        <SelectItem value="__none" disabled className="text-xs text-[#9CA3AF]">{t('noMicrophoneFound')}</SelectItem>
                      )}
                      {devices.audio.map((d, i) => (
                        <SelectItem key={d.deviceId || `mic-${i}`} value={d.deviceId || `mic-${i}`} className="text-xs">
                          {d.label || `Mikrofon ${i + 1}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="mt-4 p-3 bg-[#F3F4F1] rounded-lg">
                <p className="text-xs text-[#4B5563]">
                  <span className="font-medium">{user?.name}</span>
                  <br />{user?.email}
                </p>
              </div>
            </div>

            {error && <div className="bg-[#C87967]/10 text-[#C87967] text-sm p-3 rounded-lg" data-testid="pre-join-error">{error}</div>}

            <Button onClick={handleJoin} disabled={loading} data-testid="join-meeting-button"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-12 font-medium text-base transition-all active:scale-95">
              {loading ? '...' : t('joinMeeting')} {!loading && <ArrowRight className="w-4 h-4 ml-2" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
