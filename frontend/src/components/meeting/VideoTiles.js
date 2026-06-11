import { useEffect, useRef, useState } from 'react';

/**
 * RemoteVideo — renders a remote participant's video tile.
 * Extracted from LiveMeetingPage during the iter 215 refactor to keep the
 * page component focused on orchestration. Behavior is unchanged.
 *
 * Name resolution priority:
 *   1. REST participants list (DB-authoritative — has latest edits)
 *   2. LiveKit display name (set by backend at token-mint time)
 *   3. Email if available
 *   4. Fallback placeholder "Teilnehmer"
 */
export function RemoteVideo({ peerId, stream, participants, displayName }) {
  const videoRef = useRef(null);
  const [needsTap, setNeedsTap] = useState(false);

  useEffect(() => {
    if (!videoRef.current || !stream) return;
    videoRef.current.srcObject = stream;
    // iOS Safari blocks autoplay for videos with audio until user gesture.
    const attempt = videoRef.current.play();
    if (attempt && typeof attempt.then === 'function') {
      attempt.then(() => setNeedsTap(false)).catch(() => setNeedsTap(true));
    }
  }, [stream]);

  const handleTap = () => {
    if (videoRef.current) {
      videoRef.current.play().then(() => setNeedsTap(false)).catch(() => {});
    }
  };

  const p = participants.find(pt => pt.user_id === peerId);
  const label = p?.name || displayName || p?.email || 'Teilnehmer';

  return (
    <div className="video-tile rounded-xl relative" data-testid={`remote-video-${peerId}`}>
      <video ref={videoRef} autoPlay playsInline className="w-full h-full object-cover" />
      {needsTap && (
        <button
          onClick={handleTap}
          className="absolute inset-0 flex items-center justify-center bg-black/60 text-white text-xs font-medium"
          data-testid={`remote-tap-${peerId}`}
        >
          Tippen zum Abspielen
        </button>
      )}
      <div className="participant-name">{label}</div>
      {p?.hand_raised && <div className="absolute top-2 right-2 text-xl">✋</div>}
    </div>
  );
}

/**
 * VideoMirror — wraps a MediaStream into a <video> element. Used for the
 * local video preview when no virtual background is active.
 */
export function VideoMirror({ stream, className, style }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && stream) {
      ref.current.srcObject = stream;
      // iOS needs explicit play() to start playback in some cases
      const attempt = ref.current.play();
      if (attempt && typeof attempt.then === 'function') {
        attempt.catch(() => {});
      }
    }
  }, [stream]);
  return <video ref={ref} autoPlay muted playsInline className={className} style={style} />;
}
