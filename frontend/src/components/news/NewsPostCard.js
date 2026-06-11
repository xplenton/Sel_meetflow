import {
  Pin, AlertTriangle, ThumbsUp, MessageCircle, Clock, CheckCheck,
} from 'lucide-react';
import { useLanguage } from '../../contexts/LanguageContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const PRIORITY_CFG = {
  normal: { label: 'Normal', color: '#9CA3AF', bg: '#F3F4F1' },
  important: { label: 'Wichtig', color: '#D4A373', bg: '#D4A373' },
  critical: { label: 'Kritisch', color: '#C87967', bg: '#C87967' },
};

/**
 * NewsPostCard — one news post in the feed list. Read/unread accent bar,
 * priority dot, mandatory icon, scheduled-badge, category chips, author
 * + relative time + reaction/comment counts. Extracted from NewsPage
 * during the iter 217 refactor.
 *
 * Pure presentational — caller passes categories list and the click +
 * ref handlers; the parent owns selection & fetch state.
 */
export default function NewsPostCard({ post: p, categories, onOpen, onMountRef, formatDate }) {
  const { t } = useLanguage();
  const pri = PRIORITY_CFG[p.priority] || PRIORITY_CFG.normal;
  const isUnread = !p.is_read;
  const borderClass = p.is_mandatory && isUnread
    ? 'border-[#C87967]/40'
    : isUnread
      ? 'border-[#4A5D4E]/40'
      : 'border-[#E2E4E0]';
  const bgClass = isUnread ? 'bg-white' : 'bg-[#F9F9F8]';

  return (
    <button onClick={() => onOpen(p)}
      ref={onMountRef}
      data-post-id={p.post_id}
      className={`relative w-full text-left border rounded-xl p-4 sm:p-5 hover:border-[#4A5D4E]/30 transition-colors group ${borderClass} ${bgClass}`}
      data-testid={`news-${p.post_id}`}
      data-read={p.is_read ? 'true' : 'false'}>
      {isUnread && (
        <span
          className={`absolute left-0 top-2 bottom-2 w-1 rounded-full ${p.is_mandatory ? 'bg-[#C87967]' : 'bg-[#4A5D4E]'}`}
          aria-hidden="true"
        />
      )}
      <div className="flex gap-4">
        {p.cover_image && (
          <div className={`hidden sm:block w-24 h-24 rounded-lg overflow-hidden flex-shrink-0 bg-[#F3F4F1] ${!isUnread ? 'opacity-75' : ''}`}>
            <img src={p.cover_image.startsWith('/') ? `${API_URL}${p.cover_image}` : p.cover_image} alt="" className="w-full h-full object-cover" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            {p.pinned && <Pin className="w-3 h-3 text-[#4A5D4E]" />}
            {p.priority !== 'normal' && <span className="w-2 h-2 rounded-full" style={{ backgroundColor: pri.color }} />}
            {p.is_mandatory && isUnread && <AlertTriangle className="w-3 h-3 text-[#C87967]" />}
            {p.status === 'scheduled' && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#D4A373]/10 text-[#D4A373]" title="Zeitgesteuerte Veroeffentlichung">Geplant</span>}
            {isUnread && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#4A5D4E] text-white font-bold uppercase tracking-wider"
                data-testid={`news-unread-badge-${p.post_id}`}
              >
                {t('new') || 'Neu'}
              </span>
            )}
            {!isUnread && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full bg-[#6B8E23]/10 text-[#6B8E23] font-medium flex items-center gap-0.5"
                data-testid={`news-read-badge-${p.post_id}`}
              >
                <CheckCheck className="w-2.5 h-2.5" />
                {t('read') || 'Gelesen'}
              </span>
            )}
            {p.categories?.map(cid => {
              const cat = categories.find(c => c.category_id === cid);
              return cat ? <span key={cid} className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ backgroundColor: `${cat.color}15`, color: cat.color }}>{cat.name}</span> : null;
            })}
          </div>
          <h3 className={`text-sm transition-colors line-clamp-1 group-hover:text-[#4A5D4E] ${isUnread ? 'font-semibold text-[#1C1F1D]' : 'font-normal text-[#6B7280]'}`}>
            {p.title}
          </h3>
          {p.excerpt && <p className={`text-xs mt-0.5 line-clamp-2 ${isUnread ? 'text-[#4B5563]' : 'text-[#9CA3AF]'}`}>{p.excerpt}</p>}
          <div className="flex items-center gap-3 mt-2 text-[10px] text-[#9CA3AF]">
            <span>{p.author_name}</span>
            <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" />{formatDate(p.published_at || p.created_at)}</span>
            {(p.reaction_counts?.like > 0 || p.reaction_counts?.agree > 0 || p.reaction_counts?.helpful > 0) && (
              <span className="flex items-center gap-0.5"><ThumbsUp className="w-2.5 h-2.5" />{(p.reaction_counts?.like || 0) + (p.reaction_counts?.agree || 0) + (p.reaction_counts?.helpful || 0)}</span>
            )}
            {p.comment_count > 0 && <span className="flex items-center gap-0.5"><MessageCircle className="w-2.5 h-2.5" />{p.comment_count}</span>}
          </div>
        </div>
      </div>
    </button>
  );
}
