/**
 * Digital Signage Display (iter 131)
 *
 * Fullscreen rotating display for lobby / hall / cafeteria TVs. Designed
 * to be readable from 5 m away. No login required — the public feed at
 * `/api/news/digital-signage/feed` returns only posts explicitly tagged
 * for signage (`signage_eligible=true`) via the news-channel picker.
 *
 * URL params:
 *   ?dur=15         → rotation duration in seconds (default 15, max 120)
 *   ?theme=dark     → force a theme, overrides system preference (light|dark)
 *   ?orient=portrait → layout orientation (portrait|landscape, auto-detect default)
 *
 * Navigation: there is no UI chrome — the page is meant to be kiosk-
 * mode fullscreen. Tapping/clicking anywhere briefly shows a controls
 * overlay (prev/next/pause) that auto-hides after 3 s.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Pause, Play, AlertTriangle, Clock } from 'lucide-react';
import axios from 'axios';

const PRIORITY_COLORS = {
  critical: '#C87967',
  important: '#D4A373',
  normal: '#4A5D4E',
};
const PRIORITY_LABELS = {
  critical: 'DRINGEND',
  important: 'WICHTIG',
};

export default function DigitalSignagePage() {
  const [params] = useSearchParams();
  const rotationSec = Math.max(3, Math.min(120, parseInt(params.get('dur') || '15', 10) || 15));
  const themeParam = params.get('theme'); // 'light' | 'dark' | null (→ dark default)
  const theme = themeParam === 'light' ? 'light' : 'dark';
  const previewId = params.get('preview'); // when set → auth'd single-post preview mode

  const [posts, setPosts] = useState([]);
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [clock, setClock] = useState(new Date());
  const [controlsVisible, setControlsVisible] = useState(false);
  const controlsTimeout = useRef(null);
  const [error, setError] = useState(null);

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const fetchPosts = useCallback(async () => {
    try {
      const url = previewId
        ? `${backendUrl}/api/news/digital-signage/preview/${previewId}`
        : `${backendUrl}/api/news/digital-signage/feed`;
      const { data } = await axios.get(url, {
        params: previewId ? undefined : { limit: 30 },
        timeout: 10000,
        withCredentials: !!previewId, // preview requires auth cookie
      });
      setPosts(data?.posts || []);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Fetch failed');
    }
  }, [backendUrl, previewId]);

  // Refetch every 2 min so new signage posts appear automatically.
  // Skip the interval in preview mode — a single post doesn't change.
  useEffect(() => {
    fetchPosts();
    if (previewId) return undefined;
    const iv = setInterval(fetchPosts, 120 * 1000);
    return () => clearInterval(iv);
  }, [fetchPosts, previewId]);

  // Rotate
  useEffect(() => {
    if (paused || posts.length <= 1) return;
    const iv = setInterval(() => { setIdx(i => (i + 1) % posts.length); }, rotationSec * 1000);
    return () => clearInterval(iv);
  }, [paused, posts.length, rotationSec]);

  // Live wall clock (every 30 s is enough for a TV)
  useEffect(() => {
    const iv = setInterval(() => setClock(new Date()), 30 * 1000);
    return () => clearInterval(iv);
  }, []);

  // Reset index when posts shrink below current idx
  useEffect(() => {
    if (idx >= posts.length && posts.length > 0) setIdx(0);
  }, [posts.length, idx]);

  const showControls = useCallback(() => {
    setControlsVisible(true);
    if (controlsTimeout.current) clearTimeout(controlsTimeout.current);
    controlsTimeout.current = setTimeout(() => setControlsVisible(false), 3000);
  }, []);

  useEffect(() => () => { if (controlsTimeout.current) clearTimeout(controlsTimeout.current); }, []);

  const current = posts[idx];
  const isDark = theme === 'dark';
  const bg = isDark ? '#0F1210' : '#F9F9F6';
  const fg = isDark ? '#E8EAE6' : '#1C1F1D';
  const muted = isDark ? '#8A8F8A' : '#6B7280';
  const border = isDark ? '#2F332F' : '#E2E4E0';

  // Empty / error states
  if (error || posts.length === 0) {
    return (
      <div
        data-testid="signage-empty"
        className="w-screen h-screen flex flex-col items-center justify-center"
        style={{ background: bg, color: fg, fontFamily: 'Manrope, sans-serif' }}
      >
        <div className="text-[clamp(2rem,6vw,5rem)] font-medium tracking-tight text-center">
          MeetFlow Signage
        </div>
        <div className="text-[clamp(1rem,2vw,1.5rem)] mt-6" style={{ color: muted }}>
          {error ? 'Verbindung fehlgeschlagen – wird erneut versucht…' : 'Keine Meldungen vorhanden'}
        </div>
        <div className="mt-12 text-[clamp(3rem,8vw,6rem)] font-bold tabular-nums">
          {clock.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    );
  }

  const priorityColor = PRIORITY_COLORS[current?.priority] || PRIORITY_COLORS.normal;
  const priorityLabel = PRIORITY_LABELS[current?.priority];
  const publishedDate = current?.published_at ? new Date(current.published_at) : null;

  return (
    <div
      data-testid="signage-root"
      onClick={showControls}
      onMouseMove={showControls}
      className="w-screen h-screen overflow-hidden relative select-none cursor-none"
      style={{
        background: bg,
        color: fg,
        fontFamily: 'Manrope, sans-serif',
      }}
    >
      {/* Priority tape (full-width bar on top) for critical/important posts */}
      {priorityLabel && (
        <div
          className="absolute top-0 left-0 right-0 h-[clamp(48px,6vh,80px)] flex items-center px-[clamp(24px,4vw,80px)] z-10"
          style={{ background: priorityColor, color: '#FFFFFF' }}
        >
          <AlertTriangle className="w-[clamp(24px,3vw,48px)] h-[clamp(24px,3vw,48px)] mr-4" />
          <span className="text-[clamp(1.5rem,3vw,2.5rem)] font-bold tracking-[0.1em]">
            {priorityLabel}
          </span>
        </div>
      )}

      {/* Main content — grid: title left, clock right */}
      <div
        className="w-full h-full flex flex-col justify-between px-[clamp(40px,6vw,120px)] py-[clamp(32px,6vh,96px)]"
        style={{ paddingTop: priorityLabel ? 'clamp(96px,12vh,160px)' : 'clamp(32px,6vh,96px)' }}
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-8 flex-shrink-0">
          <div className="flex-1 min-w-0">
            {current?.category && (
              <div
                className="inline-block text-[clamp(0.875rem,1.4vw,1.25rem)] font-bold uppercase tracking-[0.2em] px-3 py-1 rounded"
                style={{ background: `${priorityColor}22`, color: priorityColor }}
              >
                {current.category}
              </div>
            )}
            <h1
              className="mt-[clamp(16px,2vh,32px)] text-[clamp(2.5rem,7vw,6rem)] font-medium leading-[1.1] tracking-tight"
              data-testid="signage-title"
            >
              {current?.title}
            </h1>
          </div>
          <div className="text-right flex-shrink-0" style={{ color: muted }}>
            <div className="text-[clamp(2.5rem,5vw,4.5rem)] font-bold tabular-nums" style={{ color: fg }}>
              {clock.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
            </div>
            <div className="text-[clamp(0.875rem,1.2vw,1.125rem)] mt-1">
              {clock.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long' })}
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 flex items-center py-[clamp(24px,4vh,64px)]">
          <div
            className="text-[clamp(1.25rem,2.4vw,2.25rem)] leading-[1.5] max-w-[80ch]"
            data-testid="signage-body"
          >
            {current?.excerpt || (current?.content?.substring(0, 280) || '') + (current?.content?.length > 280 ? ' …' : '')}
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex items-end justify-between gap-6 flex-shrink-0"
          style={{ color: muted, borderTop: `1px solid ${border}`, paddingTop: 'clamp(16px,2vh,32px)' }}
        >
          <div className="flex items-center gap-4">
            <div className="text-[clamp(0.875rem,1.2vw,1.125rem)]">
              {current?.author_name && <><strong style={{ color: fg }}>{current.author_name}</strong>{publishedDate && ' · '}</>}
              {publishedDate && publishedDate.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
            </div>
          </div>
          {/* Rotation progress dots */}
          {posts.length > 1 && (
            <div className="flex gap-2 items-center">
              {posts.slice(0, 10).map((_, i) => (
                <span
                  key={i}
                  className="rounded-full transition-all"
                  style={{
                    width: i === idx ? '24px' : '8px',
                    height: '8px',
                    background: i === idx ? priorityColor : border,
                  }}
                />
              ))}
              {posts.length > 10 && <span className="text-[0.75rem] ml-2">+{posts.length - 10}</span>}
            </div>
          )}
          <div className="text-[clamp(0.75rem,1vw,1rem)] font-medium flex items-center gap-2 opacity-60">
            <Clock className="w-4 h-4" /> MeetFlow
          </div>
        </div>
      </div>

      {/* Preview-mode banner — tells editors this is a draft preview, not live */}
      {previewId && (
        <div
          data-testid="signage-preview-banner"
          className="absolute top-4 right-4 z-30 flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold tracking-[0.15em] uppercase"
          style={{ background: '#D4A373', color: '#FFFFFF' }}
        >
          <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
          Vorschau
        </div>
      )}

      {/* Controls overlay (auto-hide) */}
      <div
        className={`absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-black/70 backdrop-blur-md rounded-full px-6 py-3 transition-opacity z-20 ${controlsVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        style={{ color: '#FFFFFF' }}
        data-testid="signage-controls"
      >
        <button
          onClick={(e) => { e.stopPropagation(); setIdx(i => (i - 1 + posts.length) % posts.length); showControls(); }}
          className="p-2 hover:bg-white/10 rounded-full"
          aria-label="Previous"
          data-testid="signage-prev"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); setPaused(p => !p); showControls(); }}
          className="p-2 hover:bg-white/10 rounded-full"
          aria-label={paused ? 'Play' : 'Pause'}
          data-testid="signage-playpause"
        >
          {paused ? <Play className="w-6 h-6" /> : <Pause className="w-6 h-6" />}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); setIdx(i => (i + 1) % posts.length); showControls(); }}
          className="p-2 hover:bg-white/10 rounded-full"
          aria-label="Next"
          data-testid="signage-next"
        >
          <ChevronRight className="w-6 h-6" />
        </button>
        <span className="text-xs font-medium opacity-70 ml-2">
          {idx + 1} / {posts.length}
        </span>
      </div>
    </div>
  );
}
