import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import NewsEditorDialog from '../components/NewsEditorDialog';
import ReportContentDialog from '../components/ReportContentDialog';
import MentionInput from '../components/MentionInput';
import AttachmentPicker, { AttachmentChip } from '../components/AttachmentPicker';
import EditorialCalendar from '../components/EditorialCalendar';
import NewsletterActions from '../components/news/NewsletterActions';
import usePullToRefresh from '../hooks/usePullToRefresh';
import PullToRefreshIndicator from '../components/PullToRefreshIndicator';
import NewsPostCard from '../components/news/NewsPostCard';
import { sanitizeHTML } from '../lib/sanitize';
import {
  Newspaper, Search, Plus, ThumbsUp, MessageCircle, Pin,
  AlertTriangle, Clock, ArrowLeft, Send, Trash2,
  Pencil, FileText, Check, CheckCheck, BarChart3,
  Flag, Bell, BellOff, X, ExternalLink, CalendarDays, Eye
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { subscribeToPush, unsubscribeFromPush, getPushSubscriptionStatus, isPushSupported } from '../lib/push';
import useNewsPostDetail from '../hooks/useNewsPostDetail';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const PRIORITY_CFG = {
  normal: { label: 'Normal', color: '#9CA3AF', bg: '#F3F4F1' },
  important: { label: 'Wichtig', color: '#D4A373', bg: '#D4A373' },
  critical: { label: 'Kritisch', color: '#C87967', bg: '#C87967' },
};

const REACTIONS = [
  { type: 'like', emoji: '👍', label: 'Gefaellt mir' },
  { type: 'agree', emoji: '✅', label: 'Zustimmung' },
  { type: 'helpful', emoji: '💡', label: 'Hilfreich' },
];

export default function NewsPage() {
  const { user } = useAuth();
  const { language, t } = useLanguage();
  const navigate = useNavigate();
  const isDE = language === 'de';
  const role = user?.role || 'member';
  const isEditor = role === 'admin' || role === 'redakteur';
  const canCreateNews = role === 'admin' || role === 'redakteur' || role === 'freigeber' || role === 'autor';
  const canReview = role === 'admin' || role === 'redakteur' || role === 'freigeber';

  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sort, setSort] = useState('latest');
  const [filterPriority, setFilterPriority] = useState('');
  const [categories, setCategories] = useState([]);
  const [filterCategory, setFilterCategory] = useState('');
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);
  // iter 167 — auto-mark news as read on scroll. An IntersectionObserver
  // watches each unread card; when it's visible for 2s, we fire the same
  // /read call the detail-view does. Already-read cards are not observed.
  const cardRefs = useRef(new Map()); // post_id -> DOM node
  const dwellTimers = useRef(new Map()); // post_id -> setTimeout id
  const observerRef = useRef(null);
  const [selectedPost, setSelectedPost] = useState(null);
  // iter 218 — Detail-view state (comments / questions / sentiment + drafts)
  // is bundled into a single hook so the page render stays focused on the
  // feed-list concerns. See `useNewsPostDetail` for the full surface.
  const detail = useNewsPostDetail();
  const {
    comments, setComments,
    commentText, setCommentText,
    commentAttachments, setCommentAttachments,
    replyingTo, setReplyingTo,
    questions, setQuestions,
    questionText, setQuestionText,
    sentiment, setSentiment,
  } = detail;
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPost, setEditingPost] = useState(null);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [groups, setGroups] = useState([]);
  const [pushStatus, setPushStatus] = useState({ supported: false, permission: 'default', subscribed: false });
  const [reportTarget, setReportTarget] = useState(null); // { type: 'post'|'comment'|'question', id, label }
  const [reportReason, setReportReason] = useState('');

  useEffect(() => {
    if (isPushSupported()) {
      getPushSubscriptionStatus().then(setPushStatus).catch(() => {});
    }
  }, []);

  const handleEnablePush = async () => {
    try {
      await subscribeToPush();
      const s = await getPushSubscriptionStatus();
      setPushStatus(s);
      toast.success('Push-Benachrichtigungen aktiviert');
    } catch (e) {
      const msg = e.message || 'Aktivierung fehlgeschlagen';
      // iter 189 — push errors are notoriously confusing on iOS/Safari.
      // Instead of a 3 s toast that disappears, link the user to /diag
      // where they can run the full push-diagnose checklist.
      toast.error(msg, {
        description: 'Klick „Zur Diagnose" unten, um den Fehler einzugrenzen.',
        action: { label: 'Zur Diagnose', onClick: () => navigate('/diag') },
        duration: 10000,
      });
    }
  };

  const handleDisablePush = async () => {
    try {
      await unsubscribeFromPush();
      const s = await getPushSubscriptionStatus();
      setPushStatus(s);
      toast.success('Push-Benachrichtigungen deaktiviert');
    } catch (e) {
      toast.error(e.message || 'Fehler');
    }
  };

  const submitReport = async () => {
    if (!reportTarget) return;
    if (!reportReason.trim()) { toast.error('Bitte Grund angeben'); return; }
    try {
      await api.post('/news/report', {
        content_type: reportTarget.type,
        content_id: reportTarget.id,
        reason: reportReason,
      });
      toast.success('Meldung eingereicht. Danke!');
      setReportTarget(null); setReportReason('');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Melden');
    }
  };

  useEffect(() => { const t = setTimeout(() => setDebouncedSearch(search), 350); return () => clearTimeout(t); }, [search]);

  useEffect(() => {
    api.get('/news/categories').then(({ data }) => setCategories(data)).catch(() => {});
    if (canCreateNews) api.get('/admin/groups').then(({ data }) => setGroups(data)).catch(() => {});
  }, [canCreateNews]);

  const fetchPosts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), limit: '15', sort });
      if (debouncedSearch) params.set('search', debouncedSearch);
      if (filterPriority) params.set('priority', filterPriority);
      if (filterCategory) params.set('category', filterCategory);
      const { data } = await api.get(`/news/feed?${params}`);
      setPosts(data.posts || []);
      setTotalPages(data.pages || 1);
    } catch { setPosts([]); }
    finally { setLoading(false); }
  }, [page, sort, debouncedSearch, filterPriority, filterCategory]);

  useEffect(() => { fetchPosts(); }, [fetchPosts]);
  useEffect(() => { setPage(1); }, [sort, debouncedSearch, filterPriority, filterCategory]);

  // iter 167 — Auto-mark-as-read via IntersectionObserver. When an unread
  // card is >=50% visible for 2s, it's considered read and we fire the
  // server-side read + flip the card's state.
  const markPostRead = useCallback((postId) => {
    setPosts(prev => {
      const target = prev.find(p => p.post_id === postId);
      if (!target || target.is_read) return prev;
      api.post(`/news/posts/${postId}/read`).catch(() => {});
      return prev.map(p => p.post_id === postId ? { ...p, is_read: true, read_at: new Date().toISOString() } : p);
    });
  }, []);

  useEffect(() => {
    // Skip on SSR / unsupported browsers.
    if (typeof IntersectionObserver === 'undefined') return;
    if (observerRef.current) observerRef.current.disconnect();
    const timers = dwellTimers.current;
    observerRef.current = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        const postId = entry.target.getAttribute('data-post-id');
        if (!postId) return;
        if (entry.isIntersecting) {
          if (!timers.has(postId)) {
            const id = setTimeout(() => {
              markPostRead(postId);
              timers.delete(postId);
            }, 2000);
            timers.set(postId, id);
          }
        } else if (timers.has(postId)) {
          clearTimeout(timers.get(postId));
          timers.delete(postId);
        }
      });
    }, { threshold: 0.5 });

    cardRefs.current.forEach((node, postId) => {
      const post = posts.find(p => p.post_id === postId);
      if (node && post && !post.is_read) observerRef.current.observe(node);
    });

    return () => {
      if (observerRef.current) observerRef.current.disconnect();
      timers.forEach(id => clearTimeout(id));
      timers.clear();
    };
  }, [posts, markPostRead]);

  const openPost = async (post) => {
    setSelectedPost(post);
    // Optimistically flip the card to "read" in the list — backend read is fire-and-forget
    setPosts(prev => prev.map(p => p.post_id === post.post_id ? { ...p, is_read: true, read_at: new Date().toISOString() } : p));
    api.post(`/news/posts/${post.post_id}/read`).catch(() => {});
    detail.load(post.post_id);
  };

  const renderPostCard = (p) => (
    <NewsPostCard
      key={p.post_id}
      post={p}
      categories={categories}
      onOpen={openPost}
      onMountRef={(el) => {
        if (el) cardRefs.current.set(p.post_id, el);
        else cardRefs.current.delete(p.post_id);
      }}
      formatDate={formatDate}
    />
  );

  const toggleReaction = async (postId, type) => {
    await api.post(`/news/posts/${postId}/reactions`, { reaction_type: type });
    if (selectedPost?.post_id === postId) {
      const { data } = await api.get(`/news/posts/${postId}`);
      setSelectedPost(data);
    }
    fetchPosts();
  };

  const addComment = async () => {
    if (!commentText.trim() && commentAttachments.length === 0) return;
    if (!selectedPost) return;
    const payload = { content: commentText };
    if (replyingTo) payload.parent_id = replyingTo.comment_id;
    if (commentAttachments.length) payload.attachments = commentAttachments.map(a => a.attachment_id);
    const { data } = await api.post(`/news/posts/${selectedPost.post_id}/comments`, payload);
    setComments(prev => [...prev, data]);
    setCommentText('');
    setCommentAttachments([]);
    setReplyingTo(null);
  };

  const deleteComment = async (cid) => {
    await api.delete(`/news/comments/${cid}`);
    setComments(prev => prev.filter(c => c.comment_id !== cid));
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000 / 60;
    if (diff < 60) return `vor ${Math.floor(diff)}m`;
    if (diff < 1440) return `vor ${Math.floor(diff / 60)}h`;
    return d.toLocaleDateString(isDE ? 'de-DE' : 'en-US', { day: '2-digit', month: '2-digit', year: '2-digit' });
  };

  // ============ POST DETAIL VIEW ============
  if (selectedPost) {
    const p = selectedPost;
    const pri = PRIORITY_CFG[p.priority] || PRIORITY_CFG.normal;
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="news-detail">
          <div className="max-w-3xl mx-auto">
            <button onClick={() => { setSelectedPost(null); fetchPosts(); }} className="flex items-center gap-1 text-sm text-[#4A5D4E] hover:underline mb-4" data-testid="back-to-feed">
              <ArrowLeft className="w-4 h-4" /> {isDE ? 'Zurück' : 'Back'}
            </button>

            <article className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
              {p.cover_image && <img src={p.cover_image.startsWith('/') ? `${API_URL}${p.cover_image}` : p.cover_image} alt="" className="w-full h-48 sm:h-64 object-cover" />}
              <div className="p-6">
                <div className="flex items-center gap-2 mb-3 flex-wrap">
                  {p.priority !== 'normal' && <Badge className="text-[10px] text-white" style={{ backgroundColor: pri.color }}>{pri.label}</Badge>}
                  {p.pinned && <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E]"><Pin className="w-2.5 h-2.5 mr-0.5" />Angepinnt</Badge>}
                  {p.is_mandatory && <Badge className="text-[10px] bg-[#C87967]/10 text-[#C87967]"><AlertTriangle className="w-2.5 h-2.5 mr-0.5" />{t('required')}</Badge>}
                  {p.status === 'scheduled' && <Badge className="text-[10px] bg-[#D4A373]/10 text-[#D4A373]" data-testid="scheduled-badge"><Clock className="w-2.5 h-2.5 mr-0.5" />Geplant</Badge>}
                  {p.expires_at && <Badge className="text-[10px] bg-[#9CA3AF]/10 text-[#9CA3AF]" title={`${t('endsOn')} ${new Date(p.expires_at).toLocaleDateString('de-DE')}`}>{t('expiresLabel')}</Badge>}
                  {(p.channels || []).filter(c => c !== 'intranet').slice(0, 3).map(c => {
                    const label = { email: 'E-Mail', push: 'Push', digital_signage: 'Screen' }[c] || c;
                    return <Badge key={c} className="text-[9px] bg-[#6B8E23]/10 text-[#6B8E23]">{label}</Badge>;
                  })}
                  {p.categories?.map(cid => {
                    const cat = categories.find(c => c.category_id === cid);
                    return cat ? <Badge key={cid} className="text-[10px]" style={{ backgroundColor: `${cat.color}15`, color: cat.color }}>{cat.name}</Badge> : null;
                  })}
                </div>

                <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1F1D] mb-2" style={{ fontFamily: 'Manrope' }}>{p.title}</h1>

                <div className="flex items-center gap-3 text-xs text-[#9CA3AF] mb-6 flex-wrap">
                  <span>{p.author_name}</span>
                  {p.owner_id && p.owner_id !== p.author_id && (
                    <span className="inline-flex items-center gap-1 text-[#6B8E23]" title="Page Owner (Verantwortlich)" data-testid="detail-owner">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#6B8E23]"></span>Owner: {p.owner_name}
                    </span>
                  )}
                  <span>{formatDate(p.published_at || p.created_at)}</span>
                  {p.is_read && <span className="flex items-center gap-0.5 text-[#6B8E23]"><CheckCheck className="w-3 h-3" />{t('read')}</span>}
                  {canReview && (p.channels || []).includes('email') && p.status === 'published' && (
                    <NewsletterActions post={p} />
                  )}
                </div>

                <div className="prose prose-sm max-w-none text-[#4B5563] leading-relaxed whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: sanitizeHTML(p.content_html || p.content) }} />

                {(p.video_url || p.embed_url) && (() => {
                  const url = p.video_url || p.embed_url;
                  let embed = null;
                  try {
                    // YouTube
                    const yt = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
                    if (yt) embed = `https://www.youtube.com/embed/${yt[1]}`;
                    // Vimeo
                    const vm = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
                    if (vm) embed = `https://player.vimeo.com/video/${vm[1]}`;
                  } catch {}
                  return (
                    <div className="mt-4 rounded-lg overflow-hidden bg-black" data-testid="news-video-embed">
                      {embed ? (
                        <div className="relative" style={{ paddingBottom: '56.25%' }}>
                          <iframe src={embed} title="Video" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen
                            className="absolute inset-0 w-full h-full border-0" />
                        </div>
                      ) : (
                        <video src={url.startsWith('/') ? `${API_URL}${url}` : url} controls className="w-full" />
                      )}
                    </div>
                  );
                })()}

                {p.external_link && (
                  <a href={p.external_link} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-2 mt-4 px-3 py-2 bg-[#4A5D4E]/10 hover:bg-[#4A5D4E]/15 text-[#4A5D4E] rounded-lg text-sm transition-colors"
                    data-testid="news-external-link">
                    <ExternalLink className="w-4 h-4" />
                    <span className="truncate">{p.external_link}</span>
                  </a>
                )}
                {p.attachments?.length > 0 && (
                  <div className="mt-6 space-y-2">
                    <p className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">Anhänge</p>
                    {p.attachments.map((att, i) => (
                      <a key={i} href={att.url?.startsWith('/') ? `${API_URL}${att.url}` : att.url} target="_blank" rel="noreferrer"
                        className="flex items-center gap-2 p-2 rounded-lg bg-[#F3F4F1] hover:bg-[#E2E4E0] transition-colors text-sm text-[#4A5D4E]">
                        <FileText className="w-4 h-4" />{att.name || 'Datei'}
                      </a>
                    ))}
                  </div>
                )}

                {p.tags?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-6">
                    {p.tags.map(tag => <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full bg-[#F3F4F1] text-[#6B7280]">#{tag}</span>)}
                  </div>
                )}

                {/* Reactions */}
                <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#E2E4E0]">
                  {REACTIONS.map(r => (
                    <button key={r.type} onClick={() => toggleReaction(p.post_id, r.type)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors ${p.user_reaction === r.type ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}
                      data-testid={`reaction-${r.type}`}>
                      <span>{r.emoji}</span>
                      <span>{p.reaction_counts?.[r.type] || 0}</span>
                    </button>
                  ))}
                  <span className="ml-auto text-xs text-[#9CA3AF] flex items-center gap-3">
                    <span className="flex items-center gap-1"><MessageCircle className="w-3.5 h-3.5" />{p.comment_count || 0}</span>
                    {p.author_id !== user?.user_id && (
                      <button onClick={() => setReportTarget({ type: 'post', id: p.post_id, label: p.title })}
                        className="text-[#9CA3AF] hover:text-[#C87967] transition-colors flex items-center gap-1" title="Beitrag melden"
                        data-testid="report-post-btn">
                        <Flag className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </span>
                </div>

                {/* Mandatory read confirmation */}
                {p.is_mandatory && !p.is_read && (
                  <div className="mt-4 p-3 bg-[#C87967]/8 border border-[#C87967]/20 rounded-lg flex items-center justify-between">
                    <span className="text-xs text-[#C87967] font-medium">{isDE ? 'Bitte Lesebestätigung abgeben' : 'Please confirm reading'}</span>
                    <Button size="sm" onClick={() => { api.post(`/news/posts/${p.post_id}/read`); setSelectedPost({ ...p, is_read: true }); toast.success('Lesebestätigung abgegeben'); }}
                      className="bg-[#C87967] hover:bg-[#B56555] text-white rounded-full text-xs h-7" data-testid="confirm-read-btn">
                      <Check className="w-3 h-3 mr-1" />{isDE ? 'Gelesen' : 'Read'}
                    </Button>
                  </div>
                )}

                {/* Approval Workflow (for editors/authors) */}
                {(canReview || (p.author_id === user?.user_id && p.status === 'draft')) && (p.status === 'review' || p.status === 'approval' || p.status === 'draft') && (
                  <div className="mt-4 p-3 bg-[#D4A373]/8 border border-[#D4A373]/20 rounded-lg" data-testid="approval-section">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#D4A373]">
                        {p.status === 'draft' && (p.approval_status === 'rejected' ? 'Abgelehnt' : 'Entwurf')}
                        {p.status === 'review' && 'Wartet auf Prüfung'}
                        {p.status === 'approval' && 'Wartet auf Freigabe'}
                      </span>
                      {p.rejection_reason && <span className="text-[10px] text-[#C87967]">{p.rejection_reason}</span>}
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {p.status === 'draft' && (p.author_id === user?.user_id || canReview) && (
                        <Button size="sm" onClick={async () => { await api.post(`/news/posts/${p.post_id}/submit-review`); const { data } = await api.get(`/news/posts/${p.post_id}`); setSelectedPost(data); toast.success('Zur Prüfung eingereicht'); }}
                          className="bg-[#D4A373] hover:bg-[#C49363] text-white rounded-full text-xs h-7" data-testid="submit-review-btn">
                          {t('submitForReview')}
                        </Button>
                      )}
                      {(p.status === 'review' || p.status === 'approval') && canReview && (
                        <>
                          <Button size="sm" onClick={async () => { await api.post(`/news/posts/${p.post_id}/approve-review`, {}); const { data } = await api.get(`/news/posts/${p.post_id}`); setSelectedPost(data); toast.success('Freigegeben'); }}
                            className="bg-[#6B8E23] hover:bg-[#5A7A1E] text-white rounded-full text-xs h-7" data-testid="approve-btn">
                            <Check className="w-3 h-3 mr-1" />{t('approveAction')}
                          </Button>
                          <Button size="sm" variant="outline" onClick={async () => {
                            const reason = prompt('Ablehnungsgrund:');
                            if (reason !== null) { await api.post(`/news/posts/${p.post_id}/reject`, { reason }); const { data } = await api.get(`/news/posts/${p.post_id}`); setSelectedPost(data); toast.success('Abgelehnt'); }
                          }} className="rounded-full text-xs h-7 border-[#C87967] text-[#C87967]" data-testid="reject-btn">
                            {t('rejectAction')}
                          </Button>
                        </>
                      )}
                      {(isEditor || (p.author_id === user?.user_id && p.status === 'draft')) && (
                        <Button size="sm" variant="ghost" onClick={() => { setEditingPost(p); setEditorOpen(true); }} className="text-xs h-7 text-[#4A5D4E]" data-testid="edit-post-btn">
                          <Pencil className="w-3 h-3 mr-1" />Bearbeiten
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </article>

            {/* Comments */}
            <div className="mt-6 bg-white border border-[#E2E4E0] rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">{isDE ? 'Kommentare' : 'Comments'} ({comments.length})</h3>
                {p.comments_enabled === false && (
                  <span className="text-[10px] text-[#9CA3AF] italic">{isDE ? 'Kommentare deaktiviert' : 'Comments disabled'}</span>
                )}
              </div>
              <div className="space-y-3">
                {(() => {
                  const topLevel = comments.filter(c => !c.parent_id);
                  const repliesByParent = comments.reduce((acc, c) => {
                    if (c.parent_id) { (acc[c.parent_id] = acc[c.parent_id] || []).push(c); }
                    return acc;
                  }, {});
                  const renderComment = (c, depth = 0) => (
                    <div key={c.comment_id} className={`flex gap-3 group ${depth > 0 ? 'ml-8 border-l-2 border-[#E2E4E0] pl-3' : ''}`}
                      data-testid={`comment-${c.comment_id}`}>
                      <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E] flex-shrink-0">
                        {c.user_name?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-medium text-[#1C1F1D]">{c.user_name}</span>
                          <span className="text-[10px] text-[#9CA3AF]">{formatDate(c.created_at)}</span>
                          {(c.user_id === user?.user_id || isEditor) && (
                            <button onClick={() => deleteComment(c.comment_id)} className="opacity-0 group-hover:opacity-100 text-[#C87967] transition-opacity" title="Löschen"><Trash2 className="w-3 h-3" /></button>
                          )}
                          {c.user_id !== user?.user_id && (
                            <button onClick={() => setReportTarget({ type: 'comment', id: c.comment_id, label: c.content.slice(0, 60) })}
                              className="opacity-0 group-hover:opacity-100 text-[#9CA3AF] hover:text-[#C87967] transition-opacity" title="Melden"
                              data-testid={`report-comment-${c.comment_id}`}>
                              <Flag className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                        <p className="text-sm text-[#4B5563] mt-0.5" dangerouslySetInnerHTML={{ __html: sanitizeHTML(
                          (c.content || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                            .replace(/@([A-Za-z0-9_\u00C0-\u017F.\-]+)/g, '<span class="text-[#4A5D4E] font-medium">@$1</span>')
                        ) }} />
                        {c.attachments && c.attachments.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-2" data-testid={`comment-attachments-${c.comment_id}`}>
                            {c.attachments.map(a => <AttachmentChip key={a.attachment_id} att={a} />)}
                          </div>
                        )}
                        {depth === 0 && p.comments_enabled !== false && (
                          <button onClick={() => { setReplyingTo(c); setCommentText(''); }}
                            className="text-[10px] text-[#9CA3AF] hover:text-[#4A5D4E] mt-0.5" data-testid={`reply-btn-${c.comment_id}`}>
                            Antworten
                          </button>
                        )}
                      </div>
                    </div>
                  );
                  return (
                    <>
                      {topLevel.map(c => (
                        <div key={c.comment_id} className="space-y-2">
                          {renderComment(c, 0)}
                          {(repliesByParent[c.comment_id] || []).map(r => renderComment(r, 1))}
                        </div>
                      ))}
                    </>
                  );
                })()}
              </div>
              {replyingTo && (
                <div className="flex items-center justify-between mt-2 px-3 py-1.5 bg-[#F3F4F1] rounded-lg">
                  <span className="text-[10px] text-[#6B7280]">{t('replyTo')} <strong>{replyingTo.user_name}</strong></span>
                  <button onClick={() => setReplyingTo(null)} className="text-[#9CA3AF] hover:text-[#6B7280]" data-testid="cancel-reply">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              )}
              <div className="mt-4 pt-3 border-t border-[#E2E4E0]">
                {p.comments_enabled === false ? (
                  <div className="text-xs text-[#9CA3AF] italic py-1">{isDE ? 'Kommentare sind für diesen Beitrag deaktiviert.' : 'Comments are disabled for this post.'}</div>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <MentionInput value={commentText} onChange={setCommentText}
                        onSubmit={addComment}
                        placeholder={isDE ? 'Kommentar schreiben... (@ für Erwaehnung)' : 'Write comment... (@ to mention)'}
                        testId="comment-input" />
                      <Button onClick={addComment} size="sm" className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl" data-testid="comment-submit">
                        <Send className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="mt-2">
                      <AttachmentPicker attachments={commentAttachments} onChange={setCommentAttachments}
                        max={5} testId="comment-attachment-picker" />
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Q&A Section */}
            <div className="mt-4 bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="qa-section">
              <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider mb-4">{isDE ? 'Fragen & Antworten' : 'Q&A'} ({questions.length})</h3>
              <div className="space-y-3">
                {questions.map(q => (
                  <div key={q.question_id} className="border border-[#E2E4E0] rounded-lg p-3" data-testid={`qa-${q.question_id}`}>
                    <div className="flex items-start gap-3">
                      <button onClick={async () => { const { data } = await api.post(`/news/questions/${q.question_id}/upvote`); setQuestions(prev => prev.map(x => x.question_id === q.question_id ? { ...x, upvote_count: data.upvote_count, user_upvoted: data.user_upvoted } : x)); }}
                        className={`flex flex-col items-center gap-0.5 flex-shrink-0 pt-0.5 ${q.user_upvoted ? 'text-[#4A5D4E]' : 'text-[#9CA3AF]'}`} data-testid={`upvote-${q.question_id}`}>
                        <ThumbsUp className="w-3.5 h-3.5" />
                        <span className="text-[10px] font-medium">{q.upvote_count || 0}</span>
                      </button>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-[#1C1F1D]">{q.text}</p>
                        <span className="text-[10px] text-[#9CA3AF]">{q.user_name} - {formatDate(q.created_at)}</span>
                        {q.answer && (
                          <div className="mt-2 p-2 bg-[#6B8E23]/8 border border-[#6B8E23]/15 rounded-lg">
                            <p className="text-xs text-[#4A5D4E]"><span className="font-medium">{q.answered_by}:</span> {q.answer}</p>
                          </div>
                        )}
                        {isEditor && !q.answer && (
                          <button onClick={async () => {
                            const ans = prompt('Antwort:');
                            if (ans) { await api.post(`/news/questions/${q.question_id}/answer`, { answer: ans }); api.get(`/news/posts/${p.post_id}/questions`).then(({ data }) => setQuestions(data)); }
                          }} className="text-[10px] text-[#4A5D4E] hover:underline mt-1" data-testid={`answer-${q.question_id}`}>Antworten</button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 mt-3 pt-3 border-t border-[#E2E4E0]">
                <Input value={questionText} onChange={e => setQuestionText(e.target.value)} placeholder={isDE ? 'Frage stellen...' : 'Ask question...'}
                  className="flex-1 border-[#E2E4E0] rounded-xl text-sm" data-testid="qa-input"
                  onKeyDown={async e => {
                    if (e.key === 'Enter' && questionText.trim()) {
                      const { data } = await api.post(`/news/posts/${p.post_id}/questions`, { text: questionText });
                      setQuestions(prev => [...prev, data]); setQuestionText('');
                    }
                  }} />
                <Button size="sm" onClick={async () => {
                  if (!questionText.trim()) return;
                  const { data } = await api.post(`/news/posts/${p.post_id}/questions`, { text: questionText });
                  setQuestions(prev => [...prev, data]); setQuestionText('');
                }} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl" data-testid="qa-submit">
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Sentiment Analysis (editor only) */}
            {isEditor && comments.length > 0 && (
              <div className="mt-4 bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="sentiment-section">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">{isDE ? 'Stimmungsanalyse' : 'Sentiment Analysis'}</h3>
                  <Button size="sm" variant="outline" onClick={async () => {
                    toast.info('Analyse laeuft...');
                    const { data } = await api.get(`/news/posts/${p.post_id}/sentiment`);
                    setSentiment(data);
                  }} className="rounded-full text-xs h-7 border-[#E2E4E0]" data-testid="run-sentiment-btn">
                    <BarChart3 className="w-3 h-3 mr-1" />{isDE ? 'Analysieren' : 'Analyze'}
                  </Button>
                </div>
                {sentiment && (
                  <div>
                    <div className="flex items-center gap-4 mb-3">
                      <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-[#6B8E23]" /><span className="text-xs text-[#6B7280]">Positiv: {sentiment.sentiment_summary?.positive || 0}</span></div>
                      <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-[#D4A373]" /><span className="text-xs text-[#6B7280]">Neutral: {sentiment.sentiment_summary?.neutral || 0}</span></div>
                      <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-[#C87967]" /><span className="text-xs text-[#6B7280]">Negativ: {sentiment.sentiment_summary?.negative || 0}</span></div>
                    </div>
                    <div className="h-3 rounded-full bg-[#F3F4F1] overflow-hidden flex">
                      {sentiment.comments > 0 && <>
                        <div className="h-full bg-[#6B8E23]" style={{ width: `${(sentiment.sentiment_summary?.positive || 0) / sentiment.comments * 100}%` }} />
                        <div className="h-full bg-[#D4A373]" style={{ width: `${(sentiment.sentiment_summary?.neutral || 0) / sentiment.comments * 100}%` }} />
                        <div className="h-full bg-[#C87967]" style={{ width: `${(sentiment.sentiment_summary?.negative || 0) / sentiment.comments * 100}%` }} />
                      </>}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </main>

        {/* Report Dialog (detail view) */}
        <ReportContentDialog target={reportTarget} reason={reportReason}
          onReasonChange={setReportReason}
          onCancel={() => { setReportTarget(null); setReportReason(''); }}
          onSubmit={submitReport} isDE={isDE} />
      </div>
    );
  }

  // ============ FEED VIEW ============
  // iter 317 — pull-to-refresh on mobile
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const ptr = usePullToRefresh({ onRefresh: fetchPosts });

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in"
            data-testid="news-page"
            {...ptr.bind}
            style={{ touchAction: ptr.isPulling ? 'none' : undefined }}>
        <PullToRefreshIndicator pullPx={ptr.pullPx} refreshing={ptr.refreshing} threshold={ptr.threshold} />
        <div className="max-w-4xl mx-auto">

          {/* Header - mobile: stacked, desktop: row */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5 sm:mb-6">
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>News</h1>
              <p className="text-xs sm:text-sm text-[#9CA3AF]">{isDE ? 'Neuigkeiten & Mitteilungen' : 'News & Announcements'}</p>
            </div>
            <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin -mx-1 px-1 sm:mx-0 sm:px-0 sm:flex-wrap sm:justify-end">
              {pushStatus.supported && (
                pushStatus.subscribed && pushStatus.permission === 'granted' ? (
                  <Button variant="outline" size="sm" onClick={handleDisablePush}
                    className="rounded-full border-[#E2E4E0] text-xs h-9 gap-1.5 flex-shrink-0" data-testid="push-disable-btn">
                    <Bell className="w-3.5 h-3.5 text-[#6B8E23]" />
                    <span className="hidden sm:inline">{isDE ? 'Push aktiv' : 'Push on'}</span>
                  </Button>
                ) : pushStatus.permission === 'denied' ? (
                  <span className="text-[10px] text-[#C87967] flex items-center gap-1 flex-shrink-0" title={t('allowNotificationsHint')}>
                    <BellOff className="w-3.5 h-3.5" /><span className="hidden sm:inline">{isDE ? 'Push blockiert' : 'Push blocked'}</span>
                  </span>
                ) : (
                  <Button variant="outline" size="sm" onClick={handleEnablePush}
                    className="rounded-full border-[#E2E4E0] text-xs h-9 gap-1.5 flex-shrink-0" data-testid="push-enable-btn">
                    <BellOff className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">{isDE ? 'Push aktivieren' : 'Enable push'}</span>
                  </Button>
                )
              )}
              {canCreateNews && (
                <Button variant="outline" size="sm" onClick={() => setCalendarOpen(true)} className="rounded-xl border-[#E2E4E0] text-xs h-9 gap-1.5 flex-shrink-0" data-testid="open-editorial-calendar">
                  <CalendarDays className="w-3.5 h-3.5" /><span className="hidden sm:inline">{isDE ? 'Redaktions-Kalender' : 'Editorial Calendar'}</span>
                </Button>
              )}
              {canCreateNews && (
                <Button size="sm" onClick={() => { setEditingPost(null); setEditorOpen(true); }} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl text-xs h-9 gap-1.5 flex-shrink-0" data-testid="create-news-btn">
                  <Plus className="w-4 h-4" /><span className="hidden sm:inline">{isDE ? 'News erstellen' : 'Create News'}</span><span className="sm:hidden">{isDE ? 'Neu' : 'New'}</span>
                </Button>
              )}
            </div>
          </div>

          {/* Filters — mobile: wrap with horizontal scroll for tabs */}
          <div className="flex flex-col sm:flex-row flex-wrap gap-2 mb-4">
            <div className="relative flex-1 min-w-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
              <Input value={search} onChange={e => setSearch(e.target.value)} placeholder={isDE ? 'News durchsuchen...' : 'Search news...'}
                className="pl-10 border-[#E2E4E0] rounded-xl h-9 text-sm w-full" data-testid="news-search" />
            </div>
            <Tabs value={sort} onValueChange={setSort} className="w-full sm:w-auto">
              <TabsList className="bg-[#F3F4F1] rounded-lg h-9 w-full sm:w-auto">
                <TabsTrigger value="latest" className="text-xs rounded-lg flex-1 sm:flex-none" data-testid="sort-latest">{isDE ? 'Aktuell' : 'Latest'}</TabsTrigger>
                <TabsTrigger value="relevance" className="text-xs rounded-lg flex-1 sm:flex-none" data-testid="sort-relevance">{isDE ? 'Relevanz' : 'Relevance'}</TabsTrigger>
                <TabsTrigger value="priority" className="text-xs rounded-lg flex-1 sm:flex-none" data-testid="sort-priority">{isDE ? 'Prioritaet' : 'Priority'}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Category + Priority Chips - horizontally scrollable on mobile */}
          {/* Iter 357 — Mobile-UX: snap-x für sauberen Touch-Scroll, größere
             Pill-Padding (py-1.5) für besseres Tap-Target. */}
          <div className="flex gap-1.5 mb-5 overflow-x-auto scrollbar-thin -mx-1 px-1 sm:flex-wrap sm:mx-0 sm:px-0 sm:overflow-visible pb-1 snap-x scroll-px-1">
            <button
              onClick={() => setShowUnreadOnly(v => !v)}
              className={`flex-shrink-0 snap-start px-2.5 py-1.5 rounded-full text-[11px] transition-colors flex items-center gap-1 ${showUnreadOnly ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}
              data-testid="filter-unread-only"
              title={isDE ? 'Nur ungelesene anzeigen' : 'Show only unread'}
            >
              <Eye className="w-3 h-3" />
              {isDE ? 'Ungelesen' : 'Unread'}
            </button>
            <button onClick={() => setFilterPriority('')} className={`flex-shrink-0 snap-start px-2.5 py-1.5 rounded-full text-[11px] transition-colors ${!filterPriority ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}>Alle</button>
            {Object.entries(PRIORITY_CFG).map(([k, v]) => (
              <button key={k} onClick={() => setFilterPriority(k === filterPriority ? '' : k)}
                className={`flex-shrink-0 snap-start px-2.5 py-1.5 rounded-full text-[11px] transition-colors ${filterPriority === k ? 'text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}
                style={filterPriority === k ? { backgroundColor: v.color } : {}}>{v.label}</button>
            ))}
            {categories.map(cat => (
              <button key={cat.category_id} onClick={() => setFilterCategory(cat.category_id === filterCategory ? '' : cat.category_id)}
                className={`flex-shrink-0 snap-start px-2.5 py-1.5 rounded-full text-[11px] transition-colors ${filterCategory === cat.category_id ? 'text-white' : 'hover:bg-[#E2E4E0]'}`}
                style={filterCategory === cat.category_id ? { backgroundColor: cat.color, color: 'white' } : { backgroundColor: `${cat.color}15`, color: cat.color }}
                data-testid={`cat-${cat.category_id}`}>
                {cat.name}
              </button>
            ))}
          </div>

          {/* Posts List */}
          {loading ? (
            <div className="text-center py-16 text-[#9CA3AF]">{t('loading')}</div>
          ) : posts.length === 0 ? (
            <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
              <Newspaper className="w-12 h-12 text-[#E2E4E0] mx-auto mb-3" />
              <p className="text-sm text-[#9CA3AF]">{isDE ? 'Keine News gefunden' : 'No news found'}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {(() => {
                const visible = showUnreadOnly ? posts.filter(p => !p.is_read) : posts;
                if (showUnreadOnly && visible.length === 0) {
                  return (
                    <div className="text-center py-12 bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl" data-testid="all-read-empty">
                      <CheckCheck className="w-10 h-10 text-[#6B8E23] mx-auto mb-2" />
                      <p className="text-sm font-medium text-[#1C1F1D]">{isDE ? 'Alles gelesen!' : 'All caught up!'}</p>
                      <p className="text-xs text-[#9CA3AF] mt-0.5">{isDE ? 'Du hast keine ungelesenen News.' : 'No unread news.'}</p>
                    </div>
                  );
                }
                const pinnedPosts = visible.filter(p => p.pinned);
                const otherPosts = visible.filter(p => !p.pinned);
                return (
                  <>
                    {pinnedPosts.length > 0 && (
                      <div className="flex items-center gap-2 text-[10px] font-bold text-[#6B7280] uppercase tracking-wider mt-1 mb-1">
                        <Pin className="w-3 h-3 text-[#4A5D4E]" />
                        <span>{isDE ? 'Angepinnt' : 'Pinned'}</span>
                        <span className="flex-1 h-px bg-[#E2E4E0]" />
                      </div>
                    )}
                    {pinnedPosts.concat([]).map(p => renderPostCard(p))}
                    {pinnedPosts.length > 0 && otherPosts.length > 0 && (
                      <div className="flex items-center gap-2 text-[10px] font-bold text-[#6B7280] uppercase tracking-wider mt-4 mb-1">
                        <span>{isDE ? 'Neueste' : 'Latest'}</span>
                        <span className="flex-1 h-px bg-[#E2E4E0]" />
                      </div>
                    )}
                    {otherPosts.map(p => renderPostCard(p))}
                  </>
                );
              })()}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => i + 1).map(p => (
                <Button key={p} size="sm" variant={p === page ? 'default' : 'outline'} onClick={() => setPage(p)}
                  className={`h-8 w-8 p-0 rounded-lg text-xs ${p === page ? 'bg-[#4A5D4E] text-white' : 'border-[#E2E4E0]'}`}>{p}</Button>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* News Editor Dialog */}
      <NewsEditorDialog open={editorOpen} onClose={() => { setEditorOpen(false); setEditingPost(null); fetchPosts(); }}
        post={editingPost} categories={categories} groups={groups} isDE={isDE}
        onCategoryCreated={() => api.get('/news/categories').then(({ data }) => setCategories(data))} />

      {/* Editorial Calendar */}
      <EditorialCalendar
        open={calendarOpen}
        onClose={() => { setCalendarOpen(false); fetchPosts(); }}
        onSelectPost={(p) => { setCalendarOpen(false); setEditingPost(p); setEditorOpen(true); }}
      />

      {/* Report Dialog */}
      <ReportContentDialog target={reportTarget} reason={reportReason}
        onReasonChange={setReportReason}
        onCancel={() => { setReportTarget(null); setReportReason(''); }}
        onSubmit={submitReport} isDE={isDE} />
    </div>
  );
}

