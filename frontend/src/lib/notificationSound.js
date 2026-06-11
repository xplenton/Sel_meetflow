/**
 * Shared chat notification sound (Web Audio API).
 * Used from both ChatPage (when already viewing chat) and
 * ChatUnreadContext (when on any other page).
 *
 * iter 307 — Double-pip + early unlock + user-controllable mute.
 * iter 309 — Volume profile (low / normal / loud) persisted to localStorage.
 *
 * Why the sound was silent before despite the API call: browsers start
 * AudioContext in "suspended" state and only allow it to start producing
 * sound *after* a user gesture (click / keydown / touch). If the first chat
 * message arrives before the user has interacted with the page, the
 * oscillator runs against a suspended context and the user hears nothing.
 *
 * Fix:
 *   1) On first import we attach one-shot `pointerdown`/`keydown` listeners
 *      that resume the AudioContext *inside* a real user gesture. After
 *      that initial unlock, every subsequent `playNotificationSound()` call
 *      can produce audio even when triggered from a WS event.
 *   2) Audio is now a 2-tone pip (880 Hz → 1175 Hz) at a configurable
 *      volume profile ("low"=0.15, "normal"=0.35, "loud"=0.6) for ~280 ms,
 *      with a brief gap — attention-grabbing yet polite at default.
 *   3) Users can mute the sound by storing `chat-sound-muted=1` in
 *      localStorage (the ChatSoundToggle UI flips this flag).
 */
const MUTE_KEY = 'chat-sound-muted';
const VOLUME_KEY = 'chat-sound-volume';
const VOLUME_PROFILES = { low: 0.15, normal: 0.35, loud: 0.6 };

let audioCtx = null;
let unlocked = false;

function isMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    return false;
  }
}

export function setChatSoundMuted(muted) {
  try {
    if (muted) localStorage.setItem(MUTE_KEY, '1');
    else localStorage.removeItem(MUTE_KEY);
  } catch { /* ignore */ }
}

export function isChatSoundMuted() {
  return isMuted();
}

export function getChatSoundVolume() {
  try {
    const v = localStorage.getItem(VOLUME_KEY);
    if (v && VOLUME_PROFILES[v] !== undefined) return v;
  } catch { /* ignore */ }
  return 'normal';
}

export function setChatSoundVolume(profile) {
  if (!VOLUME_PROFILES[profile]) return;
  try { localStorage.setItem(VOLUME_KEY, profile); } catch { /* ignore */ }
}

export const CHAT_SOUND_PROFILES = Object.keys(VOLUME_PROFILES);

async function ensureContext() {
  if (!audioCtx || audioCtx.state === 'closed') {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    audioCtx = new Ctor();
  }
  if (audioCtx.state === 'suspended') {
    try { await audioCtx.resume(); } catch { /* ignore */ }
  }
  return audioCtx;
}

function playPip(ctx, startAt, freq, duration = 0.12, gainPeak = 0.35) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freq, startAt);
  // Quick attack, smooth release
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(gainPeak, startAt + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
  osc.start(startAt);
  osc.stop(startAt + duration + 0.02);
}

export async function playNotificationSound() {
  if (isMuted()) return;
  try {
    const ctx = await ensureContext();
    if (!ctx || ctx.state !== 'running') return;
    const now = ctx.currentTime;
    const peak = VOLUME_PROFILES[getChatSoundVolume()] || VOLUME_PROFILES.normal;
    // Double-pip: 880 Hz → short gap → 1175 Hz
    playPip(ctx, now, 880, 0.12, peak);
    playPip(ctx, now + 0.16, 1175, 0.12, peak);
  } catch { /* ignore — sound is non-critical */ }
}

// One-time AudioContext unlock on the first real user gesture.
// Must run inside the actual event handler (browsers check the call stack
// for user-activation), so we use `{ once: true }` and resume synchronously.
function attachUnlock() {
  if (typeof window === 'undefined' || unlocked) return;
  const unlock = () => {
    if (unlocked) return;
    unlocked = true;
    try {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return;
      if (!audioCtx || audioCtx.state === 'closed') audioCtx = new Ctor();
      // Resume from within the gesture — this is what browsers gate on.
      if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    } catch { /* ignore */ }
  };
  ['pointerdown', 'keydown', 'touchstart'].forEach(evt => {
    window.addEventListener(evt, unlock, { once: true, passive: true });
  });
}
attachUnlock();
