import { useState, useEffect, useRef } from 'react';
import { Play, Pause } from 'lucide-react';

// Voice message player with play/pause + progress.
export default function VoicePlayer({ src, duration }) {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const audioRef = useRef(null);
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => setProgress(audio.currentTime / (audio.duration || 1) * 100);
    const onEnd = () => { setPlaying(false); setProgress(0); };
    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('ended', onEnd);
    return () => { audio.removeEventListener('timeupdate', onTime); audio.removeEventListener('ended', onEnd); };
  }, []);
  const toggle = () => { if (playing) audioRef.current?.pause(); else audioRef.current?.play(); setPlaying(!playing); };
  return (
    <div className="flex items-center gap-2 min-w-[180px]">
      <audio ref={audioRef} src={src} preload="metadata" />
      <button onClick={toggle} className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
        {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
      </button>
      <div className="flex-1">
        <div className="h-1.5 bg-white/20 rounded-full overflow-hidden"><div className="h-full bg-white/60 rounded-full transition-all" style={{ width: `${progress}%` }} /></div>
        <span className="text-[9px] opacity-60">{duration ? `${Math.floor(duration)}s` : ''}</span>
      </div>
    </div>
  );
}
