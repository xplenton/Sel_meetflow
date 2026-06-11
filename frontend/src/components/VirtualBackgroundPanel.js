import { useEffect, useState } from 'react';
import api from '../lib/api';
import { useLanguage } from '../contexts/LanguageContext';
import { X, Eye, EyeOff, Image, Hospital } from 'lucide-react';

const BASE_BACKGROUNDS = [
  { id: 'none', label: 'None', preview: null },
  { id: 'blur', label: 'Blur', preview: null },
  { id: 'office', label: 'Office', url: 'https://images.unsplash.com/photo-1497366216548-37526070297c?w=320&q=80' },
  { id: 'nature', label: 'Nature', url: 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=320&q=80' },
  { id: 'abstract', label: 'Abstract', url: 'https://images.unsplash.com/photo-1557682250-33bd709cbe85?w=320&q=80' },
  { id: 'library', label: 'Library', url: 'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=320&q=80' },
];

export default function VirtualBackgroundPanel({ onClose, currentBg, onSelectBackground }) {
  const { t } = useLanguage();
  // iter 191 — fetch the clinic-branding official background so every staff
  // member sees "Offizieller Klinik-Hintergrund" in the picker.
  const [official, setOfficial] = useState(null);
  useEffect(() => {
    api.get('/branding/official-background').then(({ data }) => {
      if (data.enabled && data.url) setOfficial(data);
    }).catch(() => {});
  }, []);

  const backgrounds = official
    ? [BASE_BACKGROUNDS[0], BASE_BACKGROUNDS[1],
       { id: 'official', label: official.name || 'Klinik', url: official.url, official: true },
       ...BASE_BACKGROUNDS.slice(2)]
    : BASE_BACKGROUNDS;

  return (
    <div className="glass-panel rounded-2xl p-4 w-[360px]" data-testid="virtual-bg-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-[#1C1F1D]">{t('virtualBackground')}</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]" data-testid="close-bg-panel"><X className="w-4 h-4" /></button>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {backgrounds.map(bg => (
          <button key={bg.id} onClick={() => onSelectBackground(bg)}
            data-testid={`bg-${bg.id}`}
            className={`relative rounded-xl overflow-hidden h-16 border-2 transition-all
              ${currentBg === bg.id ? 'border-[#4A5D4E] ring-2 ring-[#4A5D4E]/20' : 'border-[#E2E4E0] hover:border-[#4A5D4E]/40'}`}>
            {bg.url ? (
              <img src={bg.url} alt={bg.label} className="w-full h-full object-cover" />
            ) : bg.id === 'blur' ? (
              <div className="w-full h-full bg-gradient-to-br from-[#4A5D4E]/20 to-[#4A5D4E]/5 flex items-center justify-center">
                <EyeOff className="w-5 h-5 text-[#4A5D4E]" />
              </div>
            ) : (
              <div className="w-full h-full bg-[#1A1D1B] flex items-center justify-center">
                <Eye className="w-5 h-5 text-white/40" />
              </div>
            )}
            {bg.official && (
              <span className="absolute top-1 right-1 bg-[#4A5D4E] text-white rounded-full p-0.5" title="Offizieller Klinik-Hintergrund">
                <Hospital className="w-2.5 h-2.5" />
              </span>
            )}
            <span className="absolute bottom-0 inset-x-0 bg-black/50 text-white text-[9px] text-center py-0.5 font-medium truncate px-1">
              {bg.label}
            </span>
          </button>
        ))}
      </div>

      <p className="text-[9px] text-[#9CA3AF] mt-2 text-center">
        {currentBg === 'blur' ? t('backgroundBlur') + ' active' :
         currentBg !== 'none' ? t('backgroundImage') + ' active' :
         t('backgroundNone')}
      </p>
    </div>
  );
}

export { BASE_BACKGROUNDS as BACKGROUNDS };
