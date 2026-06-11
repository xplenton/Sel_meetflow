import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { flushSync } from 'react-dom';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import MeetingControls from '../components/MeetingControls';
import DocumentViewer from '../components/DocumentViewer';
import WhiteboardPanel from '../components/WhiteboardPanel';
import VirtualBackgroundPanel from '../components/VirtualBackgroundPanel';
import InviteModal from '../components/InviteModal';
import ConsentDialog from '../components/ConsentDialog';
import MeetingTopBar from '../components/meeting/MeetingTopBar';
import MeetingOverlays from '../components/meeting/MeetingOverlays';
import LeaveConfirmDialog from '../components/meeting/LeaveConfirmDialog';
import DeviceSettingsDialog from '../components/meeting/DeviceSettingsDialog';
import VideoGridSection from '../components/meeting/VideoGridSection';
import SidePanelsRouter from '../components/meeting/SidePanelsRouter';
import api, { API_URL } from '../lib/api';
import { toast } from 'sonner';
import { Room, RoomEvent, Track, ConnectionState, VideoPresets } from 'livekit-client';

/**
 * Unified meeting page (iter 140).
 *
 * Media transport: LiveKit SFU (mesh WebRTC was removed).
 * All extended features (chat, hand raise, reactions, whiteboard, breakout,
 * documents, signatures, recording, transcript, virtual background) continue
 * to use the dedicated meeting WebSocket at `/api/ws/{meeting_id}` — LiveKit
 * carries audio/video only, every other collaboration signal flows over the
 * existing WS.
 */

export default function LiveMeetingPage() {
  const { meetingId } = useParams();
  const { user } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const [meeting, setMeeting] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [micOn, setMicOn] = useState(location.state?.micOn ?? true);
  const [cameraOn, setCameraOn] = useState(location.state?.cameraOn ?? true);
  const [handRaised, setHandRaised] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [participantsOpen, setParticipantsOpen] = useState(false);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [bgPanelOpen, setBgPanelOpen] = useState(false);
  const [hostPanelOpen, setHostPanelOpen] = useState(false);
  const [virtualBg, setVirtualBg] = useState('none');
  // iter 191 — custom URL for the "official" clinic background (or any
  // future non-preset BG). Resolved via /api/branding/official-background.
  const [virtualBgUrl, setVirtualBgUrl] = useState(null);
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [activeConsent, setActiveConsent] = useState(null);
  const [remoteStreams, setRemoteStreams] = useState({});
  const [remoteNames, setRemoteNames] = useState({});
  const [reactions, setReactions] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [modeConfig, setModeConfig] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [presentedDoc, setPresentedDoc] = useState(null);
  const [signatureRequested, setSignatureRequested] = useState(null);
  const [whiteboardOpen, setWhiteboardOpen] = useState(false);
  const [subtitlesOn, setSubtitlesOn] = useState(false);
  const [subtitleText, setSubtitleText] = useState('');
  const [subtitleSender, setSubtitleSender] = useState('');
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
  const [sigVersion, setSigVersion] = useState(0);
  const [deviceSettingsOpen, setDeviceSettingsOpen] = useState(false);
  const [devices, setDevices] = useState({ video: [], audio: [] });
  const [selectedVideoDevice, setSelectedVideoDevice] = useState('');
  const [selectedAudioDevice, setSelectedAudioDevice] = useState('');
  const [quickScanRequest, setQuickScanRequest] = useState(null);   // for target user
  const [quickScanResult, setQuickScanResult] = useState(null);     // for host
  const recognitionRef = useRef(null);
  const subtitleTimeoutRef = useRef(null);
  // iter 211 — Mirror of `subtitlesOn` for use inside the recognition.onend
  // closure. Without this, the closure captures the value at toggle-time
  // (false) and the speech-recognition restart-loop never runs after the
  // first utterance, so subtitles silently stop forever.
  const subtitlesOnRef = useRef(false);

  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const localVideoRef = useRef(null);
  const wsRef = useRef(null);
  const joinTimeRef = useRef(Date.now());
  const mediaRecorderRef = useRef(null);
  const recordedChunksRef = useRef([]);
  // LiveKit room — replaces the mesh peerConnection map (iter 140).
  const livekitRoomRef = useRef(null);
  const [livekitConnected, setLivekitConnected] = useState(false);
  // iter 208 — Breakout-Room-Kontext: wenn gesetzt, joinen wir in einen
  // separaten LiveKit-Sub-Raum statt in den Hauptraum. Beendet wird der
  // Sub-Raum entweder durch `breakout-ended` (Host beendet alle) oder durch
  // den User-eigenen "Zurück zum Hauptraum"-Button.
  const [breakoutContext, setBreakoutContext] = useState(null);  // {room_id, room_name} | null
  // iter 210 — In-Meeting Einladen-Modal (Copy-Link + User-Picker + Email).
  const [inviteOpen, setInviteOpen] = useState(false);
  // iter 190 — virtual-background composite canvas + its captured MediaStream
  // track. When a BG is active this track is published in place of the raw
  // camera track, so remote participants also see the effect.
  const bgCanvasRef = useRef(null);
  const bgCanvasStreamRef = useRef(null);
  // iter 206 — flips to `true` after `<VirtualBgCanvas onPainting>` fires
  // (i.e. MediaPipe has produced its first composited frame). Until then we
  // don't replaceTrack — otherwise LiveKit publishes a blank 300×150 canvas
  // and remote participants keep seeing the raw camera.
  const [bgCanvasPainting, setBgCanvasPainting] = useState(false);
  // Keep the original camera MediaStreamTrack so we can restore it when the
  // user disables the virtual background. We grab it the very first time
  // apply() runs, before replaceTrack mutates the publication.
  const originalCamTrackRef = useRef(null);
  // Keep the initial cam/mic preference in refs so the connect effect only
  // reads them once at mount, never causing reconnects on toggle (iter 141).
  const initialCamRef = useRef(cameraOn);
  const initialMicRef = useRef(micOn);

  // Timer
  useEffect(() => {
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - joinTimeRef.current) / 1000)), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const startClientRecording = useCallback(() => {
    try {
      const stream = localStreamRef.current;
      if (!stream) { toast.error('Kein Stream zum Aufnehmen'); return; }
      recordedChunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus') ? 'video/webm;codecs=vp9,opus'
        : MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus') ? 'video/webm;codecs=vp8,opus' : 'video/webm';
      const recorder = new MediaRecorder(stream, { mimeType });
      recorder.ondataavailable = (e) => { if (e.data.size > 0) recordedChunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(recordedChunksRef.current, { type: mimeType });
        if (blob.size < 100) return;
        toast.info('Aufnahme wird hochgeladen...');
        try {
          const formData = new FormData();
          formData.append('file', blob, `recording_${meetingId}.webm`);
          await api.post(`/meetings/${meetingId}/recording/upload`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 });
          toast.success('Aufnahme gespeichert');
        } catch (err) { toast.error('Upload fehlgeschlagen'); console.error('Recording upload error:', err); }
      };
      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) { console.error('MediaRecorder error:', err); toast.error('Aufnahme konnte nicht gestartet werden'); }
  }, [meetingId]);

  const stopClientRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
  }, []);
  useEffect(() => {
    (async () => {
      try {
        // Register as participant first — idempotent, handles both the
        // "came from PreJoin" and "came directly from IncomingCall" paths
        // (iter 122). A failure here is non-fatal (e.g. already joined
        // in another tab) — we still want to render the meeting UI.
        try { await api.post(`/meetings/${meetingId}/join`); } catch {}
        const { data } = await api.get(`/meetings/${meetingId}`);
        // Canonicalize URL: if the user joined via meeting_code (e.g. from
        // a shared link), swap the URL param to the real meeting_id so WS
        // connections, LiveKit room-name and REST calls all agree — two
        // users on the same meeting must end up in the same ws_manager
        // room or chat / reactions / hand-raise won't sync (iter 144 fix).
        if (data?.meeting_id && data.meeting_id !== meetingId) {
          navigate(`/meetings/${data.meeting_id}/join`, { replace: true, state: location.state });
          return;
        }
        setMeeting(data);
        setParticipants(data.participants || []);
        const { data: msgs } = await api.get(`/meetings/${meetingId}/chat`);
        setChatMessages(msgs);
        try {
          const { data: mc } = await api.get(`/meetings/${meetingId}/mode-config`);
          setModeConfig(mc);
          if (mc.config.auto_mute) { setMicOn(false); }
        } catch {}
      } catch { toast.error('Failed to load meeting'); }
    })();
  }, [meetingId]);

  // Setup local media — iOS-friendly with error surfacing and retry
  const [mediaError, setMediaError] = useState(null); // {code,title,message}
  const isIOSDevice = useMemo(() => {
    if (typeof navigator === 'undefined') return false;
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }, []);
  const setupMedia = useCallback(async () => {
    try {
      // Pre-flight: if permissions are persistently denied, don't even
      // try getUserMedia — Chromium rejects instantly and Safari shows
      // no user-visible prompt. Surface a clear action instead (iter 122).
      try {
        if (navigator.permissions?.query) {
          const [camPerm, micPerm] = await Promise.all([
            cameraOn ? navigator.permissions.query({ name: 'camera' }).catch(() => null) : null,
            micOn ? navigator.permissions.query({ name: 'microphone' }).catch(() => null) : null,
          ]);
          const blocked = (cameraOn && camPerm?.state === 'denied') || (micOn && micPerm?.state === 'denied');
          if (blocked) {
            setMediaError({
              code: 'NotAllowed',
              title: 'Zugriff blockiert',
              message: isIOSDevice
                ? 'Einstellungen > Safari > Kamera/Mikrofon > "Erlauben" und Seite neu laden.'
                : 'Auf Schloss-Symbol in der Adressleiste klicken und Kamera/Mikrofon auf "Zulassen" setzen, dann Seite neu laden.',
            });
            // Keep-signaling flag removed (iter 140 — LiveKit handles its own).
            return;
          }
        }
      } catch { /* best-effort */ }
      const constraints = {};
      if (cameraOn) constraints.video = true;
      if (micOn) constraints.audio = true;
      if (!constraints.video && !constraints.audio) {
        // User opted to join without cam & mic (e.g. because permissions
        // are blocked). Don't force an audio request — they've made an
        // explicit choice and we'd just trigger the same error again.
        setMediaError(null);
        return;
      }
      // iter 151 — If the browser already reports permissions as `granted`,
      // SKIP the probe getUserMedia entirely. On mobile (especially iOS
      // Safari in a PWA), each getUserMedia() can re-surface the native
      // prompt even when permission is remembered, which users report as
      // "asks for camera every meeting". By relying on the Permissions API
      // result we avoid that re-prompt on subsequent joins.
      let canSkipProbe = false;
      try {
        if (navigator.permissions?.query) {
          const [camPerm, micPerm] = await Promise.all([
            cameraOn ? navigator.permissions.query({ name: 'camera' }).catch(() => null) : Promise.resolve({ state: 'granted' }),
            micOn ? navigator.permissions.query({ name: 'microphone' }).catch(() => null) : Promise.resolve({ state: 'granted' }),
          ]);
          canSkipProbe = (!cameraOn || camPerm?.state === 'granted') && (!micOn || micPerm?.state === 'granted');
        }
      } catch { /* best-effort */ }

      if (canSkipProbe) {
        // Permissions already granted — LiveKit's setCameraEnabled /
        // setMicrophoneEnabled (called from the connect() effect below)
        // will re-use the existing grant without prompting.
        setMediaError(null);
        return;
      }

      // Iter 141: LiveKit owns getUserMedia now. We only perform a
      // permission pre-flight by requesting a brief stream and stopping
      // it — this primes iOS Safari for the LiveKit publish step (which
      // won't show a second prompt because permission is cached).
      const probe = await navigator.mediaDevices.getUserMedia(constraints);
      probe.getTracks().forEach(t => { try { t.stop(); } catch {} });
      setMediaError(null);
    } catch (err) {
      console.error('Media error:', err?.name, err?.message);
      // Translate for user (iOS-aware)
      const map = {
        NotAllowedError: { code: 'NotAllowed', title: 'Zugriff verweigert',
          message: isIOSDevice
            ? 'Safari hat den Zugriff verweigert. Einstellungen > Safari > Kamera/Mikrofon > "Erlauben" und Seite neu laden.'
            : 'Browser-Berechtigungen prüfen (Schloss-Symbol in der Adressleiste -> Kamera/Mikrofon "Zulassen") und Seite neu laden.' },
        NotFoundError: { code: 'NotFound', title: 'Kein Gerät',
          message: 'Es wurde kein Kamera/Mikrofon gefunden.' },
        NotReadableError: { code: 'NotReadable', title: 'Gerät belegt',
          message: 'Das Gerät wird von einer anderen App verwendet.' },
        OverconstrainedError: { code: 'Overconstrained', title: 'Nicht unterstuetzt',
          message: 'Das Gerät erfüllt die Anforderungen nicht.' },
      };
      setMediaError(map[err?.name] || { code: 'Unknown', title: 'Fehler', message: err?.message || 'Unbekannter Fehler' });
      // Don't auto-fallback to audio-only on NotAllowedError — the user
      // has explicitly denied, a second prompt will fail just as fast
      // and the mediaError banner already offers the right actions.
      if (err?.name !== 'NotAllowedError' && cameraOn) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          localStreamRef.current = stream;
          setCameraOn(false);
        } catch {
          console.error('No media devices available');
        }
      }
    } finally {
      // iter 140 — `mediaReady` flag removed; LiveKit connects
      // independently via its own useEffect and publishes whatever tracks
      // are present in localStreamRef once its room is up.
      void 0;
    }
  }, [cameraOn, micOn, isIOSDevice]);

  // Comprehensive media release — MUST be called on every path that ends
  // the meeting (handleLeave, unmount, beforeunload). Stopping tracks only
  // in handleLeave means browser-back / tab-close leaves cam/mic LED on,
  // which users correctly perceive as a privacy bug.
  const stopAllMedia = useCallback(() => {
    try {
      localStreamRef.current?.getTracks().forEach(t => { try { t.stop(); } catch {} });
      localStreamRef.current = null;
    } catch {}
    try {
      screenStreamRef.current?.getTracks().forEach(t => { try { t.stop(); } catch {} });
      screenStreamRef.current = null;
    } catch {}
    try {
      livekitRoomRef.current?.disconnect();
      livekitRoomRef.current = null;
    } catch {}
    try {
      if (localVideoRef.current) localVideoRef.current.srcObject = null;
    } catch {}
    try {
      mediaRecorderRef.current?.stop?.();
    } catch {}
  }, []);

  useEffect(() => {
    setupMedia();
    return () => { stopAllMedia(); };
  }, []); // eslint-disable-line

  // Tab-close / refresh: cleanup in useEffect only fires on React unmount —
  // add a beforeunload listener so browser-close also releases devices.
  useEffect(() => {
    const handler = () => { stopAllMedia(); };
    window.addEventListener('beforeunload', handler);
    window.addEventListener('pagehide', handler);
    return () => {
      window.removeEventListener('beforeunload', handler);
      window.removeEventListener('pagehide', handler);
    };
  }, [stopAllMedia]);

  // LiveKit room lifecycle (iter 140). Replaces the former mesh peer-
  // connection map. We connect once `setupMedia` has resolved — the
  // publish step attaches whatever tracks we already have in
  // `localStreamRef` so "join without cam/mic" listeners remain valid.
  useEffect(() => {
    if (!meetingId || !user?.user_id) return undefined;
    let cancelled = false;
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      // iter 210 — Keep the captured mic/cam tracks alive across mute toggles
      // instead of stopping & re-acquiring them. Re-acquiring fails frequently
      // on iOS Safari and on Chrome when another tab held the device, leaving
      // the user unable to unmute. With these flags, mute/unmute simply pauses
      // the existing MediaStreamTrack — which works reliably on every browser.
      stopLocalTrackOnUnpublish: false,
      // Adaptive Simulcast — publisher sends 3 quality layers (low/med/high).
      // Subscribers auto-pick the layer matching their bandwidth, so weak
      // iPhones / slow networks get a smooth low-res feed while strong
      // laptops receive full HD without re-encoding on the server (iter 143).
      publishDefaults: {
        simulcast: true,
        videoSimulcastLayers: [VideoPresets.h180, VideoPresets.h360],
        videoCodec: 'vp8',
        stopMicTrackOnMute: false,
      },
    });
    livekitRoomRef.current = room;

    const syncLocalStreamRef = () => {
      // Mirror LiveKit's authoritative local tracks into `localStreamRef`
      // so legacy consumers (MediaRecorder for recording, Web Speech API
      // for transcript, VirtualBG canvas) get the same MediaStreamTrack
      // instances LiveKit publishes — no dual-getUserMedia race (iter 141).
      const stream = new MediaStream();
      const audioPub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      const videoPub = room.localParticipant.getTrackPublication(Track.Source.Camera);
      if (audioPub?.track?.mediaStreamTrack) stream.addTrack(audioPub.track.mediaStreamTrack);
      if (videoPub?.track?.mediaStreamTrack) stream.addTrack(videoPub.track.mediaStreamTrack);
      localStreamRef.current = stream;
      // Attach camera to local preview
      if (videoPub?.track && localVideoRef.current) {
        try { videoPub.track.attach(localVideoRef.current); } catch {}
      }
    };

    const syncRemoteStreams = () => {
      // Rebuild remoteStreams map from LiveKit's remote participants so
      // existing UI code (which keys by `peer_id`) keeps working unchanged.
      const next = {};
      const nextNames = {};
      room.remoteParticipants.forEach((p) => {
        const cam = p.getTrackPublication?.(Track.Source.Camera);
        const screen = p.getTrackPublication?.(Track.Source.ScreenShare);
        const mic = p.getTrackPublication?.(Track.Source.Microphone);
        // Prefer active screen share over camera for display tiles
        const pub = screen?.track ? screen : cam;
        const mediaStream = new MediaStream();
        if (pub?.track?.mediaStreamTrack) mediaStream.addTrack(pub.track.mediaStreamTrack);
        if (mic?.track?.mediaStreamTrack) mediaStream.addTrack(mic.track.mediaStreamTrack);
        next[p.identity] = mediaStream;
        // LiveKit's display name is set by the backend via with_name() to
        // user.name || user.email || user_id. Keep this as the authoritative
        // label so late-joiners (who aren't in the REST-loaded `participants`
        // list yet) still show a proper name instead of the raw user_id.
        if (p.name) nextNames[p.identity] = p.name;
      });
      setRemoteStreams(next);
      setRemoteNames(nextNames);
    };

    room.on(RoomEvent.ParticipantConnected, syncRemoteStreams);
    room.on(RoomEvent.ParticipantDisconnected, syncRemoteStreams);
    room.on(RoomEvent.TrackSubscribed, syncRemoteStreams);
    room.on(RoomEvent.TrackUnsubscribed, syncRemoteStreams);
    room.on(RoomEvent.TrackMuted, syncRemoteStreams);
    room.on(RoomEvent.TrackUnmuted, syncRemoteStreams);
    room.on(RoomEvent.LocalTrackPublished, syncLocalStreamRef);
    room.on(RoomEvent.LocalTrackUnpublished, syncLocalStreamRef);
    room.on(RoomEvent.ConnectionStateChanged, (state) => {
      setLivekitConnected(state === ConnectionState.Connected);
      if (state === ConnectionState.Reconnecting) toast.info('Verbindung wird wiederhergestellt…');
    });

    const connect = async () => {
      try {
        // iter 208 — wenn breakoutContext gesetzt ist, joinen wir den
        // Sub-Raum stattdessen. Endpoint validiert Membership/Host-Rechte.
        const tokenUrl = breakoutContext
          ? `/livekit/meetings/${meetingId}/breakout/${breakoutContext.room_id}/token`
          : `/livekit/meetings/${meetingId}/token`;
        const { data } = await api.post(tokenUrl);
        if (cancelled) return;
        await room.connect(data.url, data.token);
        if (cancelled) { room.disconnect(); return; }
        // Let LiveKit own getUserMedia + publishing. Previously we held
        // our own stream from setupMedia() and called publishTrack with
        // those MediaStreamTracks — that worked on iOS→others but failed
        // on laptop→others because LiveKit didn't recognise the external
        // tracks as the canonical Camera/Microphone source and never
        // set up adaptive subscriptions. Using setCameraEnabled/
        // setMicrophoneEnabled makes LiveKit create the tracks itself
        // with the correct source metadata, and remote clients subscribe
        // reliably (iter 141 fix).
        try {
          if (initialMicRef.current) await room.localParticipant.setMicrophoneEnabled(true);
        } catch (err) {
          console.warn('Mic enable failed:', err?.name);
        }
        try {
          if (initialCamRef.current) await room.localParticipant.setCameraEnabled(true);
        } catch (err) {
          console.warn('Camera enable failed:', err?.name);
        }
        syncLocalStreamRef();
        syncRemoteStreams();
      } catch (err) {
        console.error('LiveKit connect failed', err);
        toast.error('Video-Verbindung fehlgeschlagen');
      }
    };
    connect();

    return () => {
      cancelled = true;
      try { room.disconnect(); } catch {}
      livekitRoomRef.current = null;
    };
  }, [meetingId, user?.user_id, breakoutContext?.room_id]);

  // WebSocket signaling
  useEffect(() => {
    if (!user?.user_id) return;
    let ws = null;
    let cancelled = false;
    const setup = async () => {
      // Fetch a short-lived ws-token: Safari / cross-origin browsers drop
      // cookies on ws:// upgrades, so we pass the token via query-param.
      let wsToken = '';
      try {
        const { data } = await api.get('/auth/ws-token');
        wsToken = data?.token || '';
      } catch {}
      if (cancelled) return;
      const wsUrl = API_URL.replace('https://', 'wss://').replace('http://', 'ws://');
      ws = new WebSocket(`${wsUrl}/api/ws/${meetingId}/${user.user_id}${wsToken ? `?token=${wsToken}` : ''}`);
      wsRef.current = ws;

    ws.onmessage = async (event) => {
      const data = JSON.parse(event.data);

      // Iter 140: mesh WebRTC signals (peers/offer/answer/ice-candidate/
      // peer-left) are obsolete — LiveKit SFU handles media transport.
      // Silently drop them to stay compatible with any stale backend
      // broadcasters.
      if (['peers', 'peer-joined', 'offer', 'answer', 'ice-candidate', 'peer-left'].includes(data.type)) {
        return;
      }

      if (data.type === 'chat') {
        setChatMessages(prev => [...prev, data]);
      } else if (data.type === 'reaction') {
        setReactions(prev => [...prev, { id: Date.now(), emoji: data.emoji, sender: data.sender }]);
        setTimeout(() => setReactions(prev => prev.slice(1)), 2500);
      } else if (data.type === 'hand-raise') {
        // iter 211 — defensive update: if the sender isn't yet in our local
        // participants list (race during late join / list-fetch lag), append
        // a placeholder so the ✋ shows immediately. Backend has persisted
        // the new value too, so a participants refetch later only confirms.
        setParticipants(prev => {
          const exists = prev.some(p => p.user_id === data.sender);
          if (exists) {
            return prev.map(p => p.user_id === data.sender ? { ...p, hand_raised: data.raised } : p);
          }
          // Sender unknown — pull a quick participants refresh to fill in name/avatar.
          api.get(`/meetings/${meetingId}/participants`)
            .then(({ data: fresh }) => setParticipants(fresh || []))
            .catch(() => {});
          return [...prev, {
            user_id: data.sender,
            name: data.user_name || data.sender,
            email: '',
            role: 'participant',
            mic_on: true, camera_on: true,
            hand_raised: data.raised,
            joined_at: new Date().toISOString(),
            left_at: null,
          }];
        });
      } else if (data.type === 'consent-request') {
        setActiveConsent(data);
      } else if (data.type === 'consent-resolved') {
        flushSync(() => { setActiveConsent(null); });
        if (data.consent_type === 'recording') {
          startClientRecording();
        }
        if (data.result === 'approved') {
          toast.success(`${data.consent_type === 'recording' ? 'Aufnahme' : 'Transkript'} gestartet`);
        } else {
          toast.info(`${data.consent_type === 'recording' ? 'Aufnahme' : 'Transkript'} abgelehnt von ${data.declined_by}`);
        }
      } else if (data.type === 'consent-response') {
        // Another participant responded
      } else if (data.type === 'recording-stopped') {
        stopClientRecording();
        toast.info('Aufnahme gestoppt');
      } else if (data.type === 'transcript-stopped') {
        toast.info('Transkript gestoppt');
      } else if (data.type === 'host-control') {
        const isMe = data.by_id === user?.user_id;
        if (data.action === 'mute_all') {
          if (!isMe && localStreamRef.current) {
            localStreamRef.current.getAudioTracks().forEach(t => { t.enabled = false; });
            flushSync(() => { setMicOn(false); });
          }
          toast.info(`${data.by} hat alle stummgeschaltet`);
        } else if (data.action === 'unmute_all') {
          if (!isMe && localStreamRef.current) {
            localStreamRef.current.getAudioTracks().forEach(t => { t.enabled = true; });
            flushSync(() => { setMicOn(true); });
          }
          toast.info(`${data.by} hat Stummschaltung aufgehoben`);
        } else if (data.action === 'mute_user') {
          // iter 190 — host muted THIS specific participant. If I'm the
          // target, disable my local audio track (same enforcement as mute_all).
          if (data.target_user_id === user?.user_id) {
            try {
              await livekitRoomRef.current?.localParticipant?.setMicrophoneEnabled(false);
            } catch {}
            if (localStreamRef.current) {
              localStreamRef.current.getAudioTracks().forEach(t => { t.enabled = false; });
            }
            flushSync(() => { setMicOn(false); });
            toast.info(`${data.by} hat dich stummgeschaltet`);
          }
        } else if (data.action === 'disable_camera_user') {
          if (data.target_user_id === user?.user_id) {
            try {
              await livekitRoomRef.current?.localParticipant?.setCameraEnabled(false);
            } catch {}
            if (localStreamRef.current) {
              localStreamRef.current.getVideoTracks().forEach(t => { t.enabled = false; });
            }
            flushSync(() => { setCameraOn(false); });
            toast.info(`${data.by} hat deine Kamera deaktiviert`);
          }
        } else if (data.action === 'remove_user') {
          if (data.target_user_id === user?.user_id) {
            toast.error(`${data.by} hat dich aus dem Meeting entfernt`);
            setTimeout(() => handleLeave(), 2000);
          }
        } else if (data.action === 'toggle_chat') {
          flushSync(() => { setMeeting(prev => prev ? { ...prev, chat_enabled: data.value } : prev); });
          if (!isMe) toast.info(`Chat ${data.value ? 'aktiviert' : 'deaktiviert'}`);
        } else if (data.action === 'toggle_reactions') {
          flushSync(() => { setMeeting(prev => prev ? { ...prev, reactions_enabled: data.value } : prev); });
          if (!isMe) toast.info(`Reaktionen ${data.value ? 'aktiviert' : 'deaktiviert'}`);
        } else if (data.action === 'toggle_screen_share') {
          flushSync(() => { setMeeting(prev => prev ? { ...prev, screen_share_enabled: data.value } : prev); });
          if (!isMe) toast.info(`Bildschirm teilen ${data.value ? 'aktiviert' : 'deaktiviert'}`);
        }
      } else if (data.type === 'document-present') {
        if (data.presenting && data.doc_id) {
          setPresentedDoc(prev => ({
            ...(prev?.doc_id === data.doc_id ? prev : {}),
            doc_id: data.doc_id,
            current_page: data.page || 1,
            presenter: data.by,
            filename: data.filename || prev?.filename || '',
            file_ext: data.file_ext || prev?.file_ext || '',
            uploader_name: data.uploader_name || prev?.uploader_name || '',
          }));
        } else {
          setPresentedDoc(null);
        }
      } else if (data.type === 'document-page-change') {
        setPresentedDoc(prev => prev ? { ...prev, current_page: data.page } : prev);
      } else if (data.type === 'signature-request') {
        flushSync(() => { setSignatureRequested(data.doc_id); });
        toast.info(`${data.by} bittet um Unterschrift`);
        setDocsOpen(true);
      } else if (data.type === 'document-signed') {
        toast.success(`${data.signer} hat unterschrieben`);
        setSigVersion(v => v + 1);
      } else if (data.type === 'document-deleted') {
        if (presentedDoc?.doc_id === data.doc_id) setPresentedDoc(null);
        toast.info(`${data.by} hat ein Dokument gelöscht`);
      } else if (data.type === 'documents-reordered') {
        // DocumentPanel will refetch
      } else if (data.type === 'breakout-started') {
        const myRoom = data.rooms?.find(r => r.participant_ids?.includes(user?.user_id));
        if (myRoom) {
          // iter 208 — automatisch in den eigenen Gruppenraum wechseln.
          // Der LiveKit-useEffect re-connected zum Sub-Raum.
          setBreakoutContext({ room_id: myRoom.room_id, room_name: myRoom.name });
          toast.info(`Du wirst in Gruppenraum "${myRoom.name}" verschoben …`);
        } else {
          toast.info(`Breakout Rooms gestartet von ${data.by}`);
        }
      } else if (data.type === 'breakout-ended') {
        // iter 208 — beim Beenden zurück in den Hauptraum.
        setBreakoutContext(null);
        toast.info(data.by ? `Breakout Rooms beendet von ${data.by}` : 'Breakout Rooms beendet');
      } else if (data.type === 'breakout-broadcast') {
        toast.info(`[Broadcast] ${data.by}: ${data.message}`);
      } else if (data.type === 'lobby-approved' || data.type === 'lobby-rejected') {
        // Refresh participants if host
      } else if (data.type === 'subtitle') {
        setSubtitleText(data.text || '');
        setSubtitleSender(data.user_name || '');
        clearTimeout(subtitleTimeoutRef.current);
        subtitleTimeoutRef.current = setTimeout(() => { setSubtitleText(''); setSubtitleSender(''); }, 4000);
      } else if (data.type === 'quick-scan-request') {
        setQuickScanRequest({
          token: data.token,
          share_url: data.share_url,
          from_name: data.from_name,
          message: data.message,
          expires_at: data.expires_at,
        });
        toast.info(`${data.from_name} bittet um eine Schnell-Diagnose`);
      } else if (data.type === 'quick-scan-result') {
        // Only interesting for the host who sent the scan, but we broadcast
        // to the whole room so any co-host can also see it.
        setQuickScanResult({
          token: data.token,
          from_name: data.from_name,
          from_user_id: data.from_user_id,
          results: data.results,
          submitted_at: data.submitted_at,
        });
        toast.success(`Diagnose von ${data.from_name || 'Teilnehmer'} eingegangen`);
      }
    };

    ws.onclose = () => console.log('WS closed');
    ws.onerror = (e) => console.error('WS error:', e);
    };
    setup();

    return () => {
      cancelled = true;
      if (ws) ws.close();
    };
  }, [meetingId, user?.user_id]);

  // (iter 140) Mesh signaling replay useEffect removed — LiveKit handles
  // its own signaling lifecycle.

  // Toggle mic/camera — iter 141: delegate to LiveKit's native methods.
  // They own getUserMedia, deduplicate publications, and publish with
  // the correct source metadata so adaptive subscription works reliably
  // across Safari (iOS) and Chrome/Firefox (desktop).
  // iter 210 — Mic/Cam toggle: prefer mute/unmute on the existing track
  // (no re-acquisition of getUserMedia). Falls back to setMic/setCamera-Enabled
  // only when there is no published track yet (first-time enable after a
  // permanent stop). This fixes iOS Safari and Chrome cases where the device
  // wasn't released cleanly and a second getUserMedia() call would throw
  // NotReadableError or "Could not start audio source".
  const toggleMic = async () => {
    const room = livekitRoomRef.current;
    if (!room) return;
    const next = !micOn;
    try {
      const pub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      if (pub?.track) {
        if (next) await pub.unmute();
        else await pub.mute();
      } else {
        // No track published yet — actually request the device.
        await room.localParticipant.setMicrophoneEnabled(next);
      }
      setMicOn(next);
    } catch (err) {
      console.error('Mic toggle error:', err);
      toast.error('Mikrofon konnte nicht umgeschaltet werden');
    }
  };

  const toggleCamera = async () => {
    const room = livekitRoomRef.current;
    if (!room) return;
    const next = !cameraOn;
    try {
      const pub = room.localParticipant.getTrackPublication(Track.Source.Camera);
      if (pub?.track) {
        if (next) await pub.unmute();
        else await pub.mute();
      } else {
        await room.localParticipant.setCameraEnabled(next);
      }
      setCameraOn(next);
    } catch (err) {
      console.error('Camera toggle error:', err);
      toast.error('Kamera konnte nicht umgeschaltet werden');
    }
  };

  const loadDevices = useCallback(async () => {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      const video = devs.filter(d => d.kind === 'videoinput');
      const audio = devs.filter(d => d.kind === 'audioinput');
      setDevices({ video, audio });
      if (video.length && !selectedVideoDevice) {
        const currentVideoTrack = localStreamRef.current?.getVideoTracks()[0];
        setSelectedVideoDevice(currentVideoTrack?.getSettings()?.deviceId || video[0].deviceId);
      }
      if (audio.length && !selectedAudioDevice) {
        const currentAudioTrack = localStreamRef.current?.getAudioTracks()[0];
        setSelectedAudioDevice(currentAudioTrack?.getSettings()?.deviceId || audio[0].deviceId);
      }
    } catch {}
  }, [selectedVideoDevice, selectedAudioDevice]);

  const switchCamera = async (deviceId) => {
    setSelectedVideoDevice(deviceId);
    try {
      // LiveKit's built-in device switch unpublishes the old track and
      // publishes a new one with the chosen deviceId — the cleanest API
      // that also updates all remote subscribers.
      await livekitRoomRef.current?.switchActiveDevice?.('videoinput', deviceId);
      if (!cameraOn) setCameraOn(true);
    } catch { toast.error('Kamera konnte nicht gewechselt werden'); }
  };

  const switchMicrophone = async (deviceId) => {
    setSelectedAudioDevice(deviceId);
    try {
      await livekitRoomRef.current?.switchActiveDevice?.('audioinput', deviceId);
      if (!micOn) setMicOn(true);
    } catch { toast.error('Mikrofon konnte nicht gewechselt werden'); }
  };



  const handleShareScreen = async () => {
    try {
      // Prefer LiveKit's built-in toggle — it handles track lifecycle
      // (auto-unpublish on stop, re-negotiation, quality adaptation).
      const room = livekitRoomRef.current;
      if (!room) return;
      await room.localParticipant.setScreenShareEnabled(true);
      setIsScreenSharing(true);
      // Detect user-initiated "Stop sharing" via publication change.
      const onUnpublished = (pub) => {
        if (pub?.source === Track.Source.ScreenShare) {
          setIsScreenSharing(false);
          room.localParticipant.off('localTrackUnpublished', onUnpublished);
        }
      };
      room.localParticipant.on('localTrackUnpublished', onUnpublished);
    } catch { /* user cancelled picker */ }
  };

  const handleRaiseHand = () => {
    const newState = !handRaised;
    setHandRaised(newState);
    // iter 211 — Update the local participants list immediately so the ✋
    // appears on the user's own tile (used by remote-style rendering paths).
    setParticipants(prev => prev.map(p =>
      p.user_id === user?.user_id ? { ...p, hand_raised: newState } : p
    ));
    // Persist to DB so late joiners see the current state when /participants
    // is fetched. Fire-and-forget — the WS broadcast is the primary delivery.
    api.put(`/meetings/${meetingId}/participants/${user?.user_id}`, { hand_raised: newState }).catch(() => {});
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'hand-raise',
        raised: newState,
        user_name: user?.name,  // iter 211 — let receivers fill placeholder name
      }));
    }
  };

  const handleReaction = (emoji) => {
    const selected = emoji || '👍';
    wsRef.current?.send(JSON.stringify({ type: 'reaction', emoji: selected }));
    setReactions(prev => [...prev, { id: Date.now(), emoji: selected, sender: 'you' }]);
    setTimeout(() => setReactions(prev => prev.slice(1)), 2500);
  };

  const handleSendChat = async (message) => {
    try {
      await api.post(`/meetings/${meetingId}/chat`, { message });
      // Only broadcast via WS if connection is open — otherwise remote
      // clients silently miss the message. Backend persists it anyway so
      // late-joiners pick it up on the next /chat GET (iter 144).
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'chat', message, user_name: user?.name, created_at: new Date().toISOString() }));
      }
      setChatMessages(prev => [...prev, { message, user_name: user?.name, created_at: new Date().toISOString(), message_id: Date.now() }]);
    } catch {}
  };

  const handleLeave = async () => {
    try {
      stopClientRecording();
      stopAllMedia();
      wsRef.current?.close();
      await api.post(`/meetings/${meetingId}/leave`);
    } catch {}
    navigate('/dashboard', { replace: true });
  };

  // iter 190 — Virtual Background publishing to remote participants.
  // Whenever `virtualBg` is non-'none' AND the local camera is live, we grab
  // the composited canvas stream and swap it into LiveKit's published camera
  // track. Remote clients subscribe to the same Track.Source.Camera so they
  // automatically receive the composited video without any extra signaling.
  // When the effect is turned off (or the camera goes dark) we restore the
  // original MediaStreamTrack from the physical camera.
  //
  // iter 206 — gated on `bgCanvasPainting` so we only replaceTrack once the
  // canvas has produced a real frame; also re-applies on `LocalTrackPublished`
  // (covers the camera-was-off-at-mount race) and uses `userProvidedTrack=true`
  // so LiveKit doesn't reapply its own getUserMedia constraints to our canvas.
  useEffect(() => {
    if (!livekitRoomRef.current) return undefined;
    const room = livekitRoomRef.current;

    let cancelled = false;
    let retryTimer = null;

    const apply = async () => {
      // Always re-fetch the current camera publication — toggling the camera
      // off/on creates a new LocalVideoTrack, and stale closures would otherwise
      // call replaceTrack on a track that's no longer published.
      const camPub = room.localParticipant?.getTrackPublication?.(Track.Source.Camera);
      const localVideoTrack = camPub?.track;

      if (virtualBg === 'none') {
        // Restore the raw camera feed if we previously swapped in a canvas track.
        if (bgCanvasStreamRef.current && localVideoTrack) {
          try {
            const orig = originalCamTrackRef.current;
            if (orig && orig.readyState !== 'ended') {
              await localVideoTrack.replaceTrack(orig, true);
            } else {
              // Camera was stopped while effect was active — re-enable it.
              await room.localParticipant.setCameraEnabled(true);
            }
            bgCanvasStreamRef.current.getTracks().forEach(t => { try { t.stop(); } catch {} });
          } catch (err) {
            console.warn('[virtualBg] restore failed:', err);
          }
          bgCanvasStreamRef.current = null;
          originalCamTrackRef.current = null;
        }
        return;
      }

      // Virtual BG is active — we need the camera publication, the canvas
      // element AND at least one painted frame before swapping the track.
      if (!cameraOn || !localVideoTrack) {
        // Camera not yet published. The LocalTrackPublished listener below
        // will re-trigger apply() once it appears. No need to spin a retry.
        return;
      }
      const canvas = bgCanvasRef.current;
      if (!canvas || !bgCanvasPainting) {
        // Canvas mounted but MediaPipe hasn't drawn its first frame yet —
        // the bgCanvasPainting state flip will re-run this effect for us.
        return;
      }
      try {
        // Remember the real camera track once, so we can restore it cleanly.
        if (!originalCamTrackRef.current) {
          originalCamTrackRef.current = localVideoTrack.mediaStreamTrack;
        }
        // 30 fps matches the camera; lower values save CPU but look choppy.
        const compositeStream = canvas.captureStream(30);
        const compositeTrack = compositeStream.getVideoTracks()[0];
        if (!compositeTrack) return;
        if (cancelled) { compositeTrack.stop(); return; }
        // userProvidedTrack=true: LiveKit treats this as an externally-owned
        // MediaStreamTrack and does NOT try to reapply camera constraints
        // (which would silently no-op on a canvas track).
        await localVideoTrack.replaceTrack(compositeTrack, true);
        // Stop any previous canvas stream to avoid leaks.
        if (bgCanvasStreamRef.current && bgCanvasStreamRef.current !== compositeStream) {
          bgCanvasStreamRef.current.getTracks().forEach(t => { try { t.stop(); } catch {} });
        }
        bgCanvasStreamRef.current = compositeStream;
      } catch (err) {
        console.warn('[virtualBg] publish failed:', err);
      }
    };

    apply();

    // Re-apply when the camera (re-)publishes — covers two cases:
    //   1) User joined with virtualBg already set but camera publish was
    //      still in flight when the effect first fired.
    //   2) User toggled the camera off and back on while a BG was active.
    const onLocalTrackPublished = (publication) => {
      if (publication?.source === Track.Source.Camera) apply();
    };
    room.on(RoomEvent.LocalTrackPublished, onLocalTrackPublished);

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      try { room.off(RoomEvent.LocalTrackPublished, onLocalTrackPublished); } catch {}
    };
  }, [virtualBg, cameraOn, livekitConnected, bgCanvasPainting]);

  const confirmLeave = () => setLeaveDialogOpen(true);

  const handleParticipantAction = async (userId, action) => {
    try {
      if (action === 'mute') await api.put(`/meetings/${meetingId}/participants/${userId}`, { mic_on: false });
      else if (action === 'co-host') await api.put(`/meetings/${meetingId}/participants/${userId}`, { role: 'co-host' });
      else if (action === 'remove') await api.put(`/meetings/${meetingId}/participants/${userId}`, { role: 'removed' });
      else if (action === 'quick-scan') {
        const { data } = await api.post(`/meetings/${meetingId}/quick-scan/${userId}`, {});
        const target = participants.find(p => p.user_id === userId);
        toast.success(`Schnell-Diagnose an ${target?.name || 'Teilnehmer'} gesendet`, {
          description: 'Ergebnisse erscheinen hier, sobald das Gerät getestet wurde.',
        });
        try { await navigator.clipboard.writeText(data.share_url); } catch {}
        return;
      }
      const { data } = await api.get(`/meetings/${meetingId}/participants`);
      setParticipants(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Aktion fehlgeschlagen');
    }
  };

  const handleDocPageChange = async (docId, page) => {
    try {
      await api.post(`/meetings/${meetingId}/documents/${docId}/present`, {
        presenting: true, page
      });
    } catch {}
  };

  const handleStopPresentation = async () => {
    if (presentedDoc) {
      try {
        await api.post(`/meetings/${meetingId}/documents/${presentedDoc.doc_id}/present`, {
          presenting: false, page: 1
        });
      } catch {}
    }
    setPresentedDoc(null);
  };

  const closeSidePanels = (except) => {
    if (except !== 'chat') setChatOpen(false);
    if (except !== 'participants') setParticipantsOpen(false);
    if (except !== 'extras') setExtrasOpen(false);
    if (except !== 'files') setFilesOpen(false);
    if (except !== 'docs') setDocsOpen(false);
    if (except !== 'host') setHostPanelOpen(false);
    if (except !== 'whiteboard') setWhiteboardOpen(false);
  };

  const toggleSubtitles = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error('Spracherkennung wird von diesem Browser nicht unterstützt');
      return;
    }
    if (subtitlesOn) {
      subtitlesOnRef.current = false;  // iter 211 — stop auto-restart loop
      try { recognitionRef.current?.stop(); } catch {}
      recognitionRef.current = null;
      setSubtitlesOn(false);
      setSubtitleText('');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'de-DE';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) { finalText += transcript; }
        else { interimText += transcript; }
      }
      const displayText = finalText || interimText;
      if (displayText) {
        setSubtitleText(displayText);
        setSubtitleSender(user?.name || '');
        clearTimeout(subtitleTimeoutRef.current);
        subtitleTimeoutRef.current = setTimeout(() => { setSubtitleText(''); setSubtitleSender(''); }, 4000);
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'subtitle', text: displayText, user_name: user?.name }));
        }
      }
    };
    recognition.onerror = (e) => {
      // 'no-speech' fires routinely during silence; not an error.
      // 'aborted' fires when we explicitly stop — ignore.
      if (e.error && !['no-speech', 'aborted'].includes(e.error)) {
        console.error('Speech error:', e.error);
      }
    };
    // iter 211 — When recognition ends (silence timeout, network blip, mobile
    // background tab) Chrome stops emitting results unless we explicitly start
    // a new instance. We re-create the recognition from scratch so we don't
    // accidentally re-use a torn-down WebSpeech session, and gate on a ref
    // (not stale closure state) so the loop keeps running until the user
    // toggles subtitles off.
    recognition.onend = () => {
      if (!subtitlesOnRef.current) return;
      try { recognition.start(); }
      catch (e) {
        // InvalidStateError on rapid restart — wait a tick and retry once.
        setTimeout(() => { try { recognition.start(); } catch {} }, 250);
      }
    };
    try { recognition.start(); }
    catch (e) {
      console.error('Recognition start failed:', e);
      toast.error('Spracherkennung konnte nicht gestartet werden');
      return;
    }
    recognitionRef.current = recognition;
    subtitlesOnRef.current = true;  // iter 211 — must be set BEFORE the first onend can fire
    setSubtitlesOn(true);
    toast.success('Untertitel aktiviert');
  }, [subtitlesOn, user?.name]);

  const isHost = participants.find(p => p.user_id === user?.user_id)?.role === 'host';
  const remoteEntries = Object.entries(remoteStreams);
  const totalTiles = 1 + remoteEntries.length;
  const gridCols = totalTiles <= 1 ? 'grid-cols-1' : totalTiles <= 4 ? 'grid-cols-1 sm:grid-cols-2' : totalTiles <= 9 ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4';

  return (
    <div className="h-screen flex flex-col bg-[#1A1D1B]" data-testid="live-meeting-page">
      {/* iter 215 — banners + top bar extracted into MeetingTopBar to keep
          the orchestration component focused on logic. */}
      <MeetingTopBar
        meeting={meeting}
        modeConfig={modeConfig}
        isRecording={isRecording}
        isHost={isHost}
        elapsed={elapsed}
        participantsCount={participants.filter(p => p.joined_at && !p.left_at).length}
        mediaError={mediaError}
        onRetryMedia={setupMedia}
        breakoutContext={breakoutContext}
        onLeaveBreakout={() => setBreakoutContext(null)}
        formatTime={formatTime}
      />

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Video grid (iter 215 — extracted into VideoGridSection) */}
        <VideoGridSection
          user={user}
          cameraOn={cameraOn}
          micOn={micOn}
          handRaised={handRaised}
          virtualBg={virtualBg}
          virtualBgUrl={virtualBgUrl}
          localVideoRef={localVideoRef}
          localStreamRef={localStreamRef}
          bgCanvasRef={bgCanvasRef}
          onBgCanvasReady={(c) => {
            // iter 206 — reset the "first painted frame" gate every
            // time the canvas (re)mounts. The next onPainting() flips
            // it back to true and the publish-effect re-runs.
            if (c) setBgCanvasPainting(false);
          }}
          onBgPainting={() => setBgCanvasPainting(true)}
          remoteEntries={remoteEntries}
          remoteNames={remoteNames}
          participants={participants}
          presentedDoc={presentedDoc}
          whiteboardOpen={whiteboardOpen}
          gridCols={gridCols}
        />

        {/* Document Viewer (when presenting) */}
        {presentedDoc && (
          <DocumentViewer
            meetingId={meetingId}
            doc={presentedDoc}
            isPresenter={isHost}
            onClose={handleStopPresentation}
            onPageChange={handleDocPageChange}
            sigVersion={sigVersion}
          />
        )}

        {/* Whiteboard */}
        {whiteboardOpen && !presentedDoc && (
          <WhiteboardPanel
            meetingId={meetingId}
            wsRef={wsRef}
            userId={user?.user_id}
            onClose={() => setWhiteboardOpen(false)}
          />
        )}

        {/* Side panels (iter 215 — extracted into SidePanelsRouter, handles
            both desktop inline panels and mobile full-screen overlays). */}
        <SidePanelsRouter
          meeting={meeting}
          meetingId={meetingId}
          user={user}
          isHost={isHost}
          participants={participants}
          chatOpen={chatOpen} onCloseChat={() => setChatOpen(false)}
          chatMessages={chatMessages} onSendChat={handleSendChat}
          participantsOpen={participantsOpen} onCloseParticipants={() => setParticipantsOpen(false)}
          onParticipantAction={handleParticipantAction}
          extrasOpen={extrasOpen} onCloseExtras={() => setExtrasOpen(false)}
          filesOpen={filesOpen} onCloseFiles={() => setFilesOpen(false)}
          docsOpen={docsOpen} onCloseDocs={() => setDocsOpen(false)}
          presentedDoc={presentedDoc} onPresentDoc={setPresentedDoc} wsRef={wsRef}
          hostPanelOpen={hostPanelOpen} onCloseHostPanel={() => setHostPanelOpen(false)}
          onMeetingRefreshed={setMeeting}
          onRecordingStart={startClientRecording} onRecordingStop={stopClientRecording}
          breakoutContext={breakoutContext} onVisitBreakout={setBreakoutContext}
        />
      </div>

      {/* Virtual Background Panel */}
      {bgPanelOpen && (
        <div className="fixed inset-0 z-[60]" onClick={() => setBgPanelOpen(false)}>
          <div className="absolute bottom-24 left-1/2 -translate-x-1/2" onClick={e => e.stopPropagation()}>
            <VirtualBackgroundPanel currentBg={virtualBg} onClose={() => setBgPanelOpen(false)}
              onSelectBackground={(bg) => {
                setVirtualBg(bg.id);
                setVirtualBgUrl(bg.official ? bg.url : null);
                setBgPanelOpen(false);
              }} />
          </div>
        </div>
      )}

      {/* iter 215 — Quick-Scan, emoji picker, reactions and subtitle overlays
          extracted into a single MeetingOverlays component. */}
      <MeetingOverlays
        emojiPickerOpen={emojiPickerOpen}
        onCloseEmojiPicker={() => setEmojiPickerOpen(false)}
        onPickReaction={handleReaction}
        reactions={reactions}
        subtitleText={subtitleText}
        subtitleSender={subtitleSender}
        quickScanRequest={quickScanRequest}
        onDismissQuickScanRequest={() => setQuickScanRequest(null)}
        quickScanResult={quickScanResult}
        onDismissQuickScanResult={() => setQuickScanResult(null)}
      />

      {/* Leave Confirmation Dialog (extracted iter 215) */}
      <LeaveConfirmDialog
        open={leaveDialogOpen}
        onOpenChange={setLeaveDialogOpen}
        isRecording={isRecording}
        onConfirm={handleLeave}
      />

      {/* Consent Dialog */}
      <ConsentDialog consent={activeConsent} meetingId={meetingId} userId={user?.user_id}
        open={!!activeConsent}
        onResolved={() => { flushSync(() => { setActiveConsent(null); }); }} />

      {/* Controls */}
      <MeetingControls micOn={micOn} cameraOn={cameraOn} onToggleMic={toggleMic} onToggleCamera={toggleCamera}
        onShareScreen={handleShareScreen}
        onToggleChat={() => { closeSidePanels('chat'); setChatOpen(!chatOpen); }}
        onToggleParticipants={() => { closeSidePanels('participants'); setParticipantsOpen(!participantsOpen); }}
        onRaiseHand={handleRaiseHand} onLeave={confirmLeave} handRaised={handRaised}
        chatOpen={chatOpen} participantsOpen={participantsOpen} onReaction={() => setEmojiPickerOpen(!emojiPickerOpen)}
        onToggleExtras={() => { closeSidePanels('extras'); setExtrasOpen(!extrasOpen); }}
        extrasOpen={extrasOpen}
        onToggleFiles={() => { closeSidePanels('files'); setFilesOpen(!filesOpen); }}
        filesOpen={filesOpen}
        onToggleBg={() => setBgPanelOpen(!bgPanelOpen)} bgPanelOpen={bgPanelOpen}
        isHost={isHost}
        onToggleHostPanel={() => { closeSidePanels('host'); setHostPanelOpen(!hostPanelOpen); }}
        hostPanelOpen={hostPanelOpen}
        onToggleDocs={() => { closeSidePanels('docs'); setDocsOpen(!docsOpen); }}
        docsOpen={docsOpen}
        onToggleWhiteboard={() => { closeSidePanels('whiteboard'); setWhiteboardOpen(!whiteboardOpen); }}
        whiteboardOpen={whiteboardOpen}
        onToggleSubtitles={toggleSubtitles}
        subtitlesOn={subtitlesOn}
        isScreenSharing={isScreenSharing}
        onToggleDeviceSettings={() => { setDeviceSettingsOpen(!deviceSettingsOpen); if (!deviceSettingsOpen) loadDevices(); }}
        deviceSettingsOpen={deviceSettingsOpen}
        onToggleInvite={() => setInviteOpen(true)} />

      {/* iter 210 — In-Meeting Einladen-Modal (Copy-Link + User-Picker + Email) */}
      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)}
        meetingId={meetingId} meetingTitle={meeting?.title} />

      {/* Device Settings Dialog (extracted iter 215) */}
      <DeviceSettingsDialog
        open={deviceSettingsOpen}
        onOpenChange={setDeviceSettingsOpen}
        devices={devices}
        selectedVideoDevice={selectedVideoDevice}
        selectedAudioDevice={selectedAudioDevice}
        onSwitchCamera={switchCamera}
        onSwitchMic={switchMicrophone}
      />
    </div>
  );
}
