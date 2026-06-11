import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Switch } from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Upload, Image, Plus, Monitor } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import AudiencePicker from './AudiencePicker';

import { useLanguage } from '../contexts/LanguageContext';
// Convert ISO/UTC string -> local `datetime-local` value (YYYY-MM-DDTHH:mm)
function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Convert local `datetime-local` input -> ISO UTC
function localInputToIso(value) {
  if (!value) return '';
  const d = new Date(value); // datetime-local is parsed as local
  return isNaN(d.getTime()) ? '' : d.toISOString();
}

/**
 * News editor dialog (extracted from NewsPage.js for maintainability).
 */
export default function NewsEditorDialog({ open, onClose, post, categories, groups, isDE, onCategoryCreated }) {
  const { t } = useLanguage();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [excerpt, setExcerpt] = useState('');
  const [priority, setPriority] = useState('normal');
  const [pinned, setPinned] = useState(false);
  const [isMandatory, setIsMandatory] = useState(false);
  const [commentsEnabled, setCommentsEnabled] = useState(true);
  const [selectedCats, setSelectedCats] = useState([]);
  const [tags, setTags] = useState('');
  const [targetAll, setTargetAll] = useState(true);
  const [targetGroups, setTargetGroups] = useState([]);
  const [targetUserIds, setTargetUserIds] = useState([]);
  const [status, setStatus] = useState('draft');
  const [publishAt, setPublishAt] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [coverImage, setCoverImage] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [saving, setSaving] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [externalLink, setExternalLink] = useState('');
  const [targetDepartments, setTargetDepartments] = useState('');
  const [targetLocations, setTargetLocations] = useState('');
  const [targetProfessions, setTargetProfessions] = useState('');
  const [targetRoles, setTargetRoles] = useState([]);
  // Governance fields (Page Owner + Channels)
  const [ownerId, setOwnerId] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [channels, setChannels] = useState(['intranet']);

  useEffect(() => {
    if (post) {
      setTitle(post.title || ''); setContent(post.content || '');
      setExcerpt(post.excerpt || ''); setPriority(post.priority || 'normal');
      setPinned(post.pinned || false); setIsMandatory(post.is_mandatory || false);
      setCommentsEnabled(post.comments_enabled !== false);
      setSelectedCats(post.categories || []); setTags((post.tags || []).join(', '));
      setTargetAll(post.target_all !== false); setTargetGroups(post.target_groups || []);
      setTargetUserIds(post.target_user_ids || []);
      setTargetDepartments((post.target_departments || []).join(', '));
      setTargetLocations((post.target_locations || []).join(', '));
      setTargetProfessions((post.target_professions || []).join(', '));
      setTargetRoles(post.target_roles || []);
      setVideoUrl(post.video_url || post.embed_url || '');
      setExternalLink(post.external_link || '');
      setStatus(post.status || 'draft'); setPublishAt(post.publish_at || '');
      setExpiresAt(post.expires_at || ''); setCoverImage(post.cover_image || '');
      setAttachments(post.attachments || []);
      setOwnerId(post.owner_id || '');
      setOwnerName(post.owner_name || '');
      setChannels(post.channels && post.channels.length > 0 ? post.channels : ['intranet']);
    } else {
      setTitle(''); setContent(''); setExcerpt(''); setPriority('normal');
      setPinned(false); setIsMandatory(false); setCommentsEnabled(true);
      setSelectedCats([]); setTags('');
      setTargetAll(true); setTargetGroups([]); setTargetUserIds([]); setStatus('draft');
      setTargetDepartments(''); setTargetLocations(''); setTargetProfessions(''); setTargetRoles([]);
      setVideoUrl(''); setExternalLink('');
      setPublishAt(''); setExpiresAt(''); setCoverImage(''); setAttachments([]);
      setOwnerId(''); setOwnerName(''); setChannels(['intranet']);
    }
  }, [post, open]);

  const handleSave = async (saveStatus) => {
    if (!title.trim()) { toast.error('Titel erforderlich'); return; }
    setSaving(true);
    try {
      const splitList = (s) => (s || '').split(',').map(x => x.trim()).filter(Boolean);
      const payload = {
        title, content, content_html: content, excerpt, priority, pinned, is_mandatory: isMandatory,
        comments_enabled: commentsEnabled,
        categories: selectedCats, tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        target_all: targetAll, target_groups: targetGroups, target_user_ids: targetUserIds, status: saveStatus || status,
        target_departments: splitList(targetDepartments),
        target_locations: splitList(targetLocations),
        target_professions: splitList(targetProfessions),
        target_roles: targetRoles,
        video_url: videoUrl, external_link: externalLink,
        publish_at: publishAt, expires_at: expiresAt, cover_image: coverImage, attachments,
        owner_id: ownerId || undefined, channels,
      };
      if (post?.post_id) {
        await api.put(`/news/posts/${post.post_id}`, payload);
        toast.success('News aktualisiert');
      } else {
        await api.post('/news/posts', payload);
        toast.success(saveStatus === 'published' ? 'News veroeffentlicht' : 'Entwurf gespeichert');
      }
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setSaving(false); }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const { data } = await api.post('/news/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (file.type.startsWith('image/')) setCoverImage(data.url);
      else setAttachments(prev => [...prev, { url: data.url, name: file.name }]);
      toast.success('Datei hochgeladen');
    } catch { toast.error('Upload fehlgeschlagen'); }
  };

  const createCategory = async () => {
    if (!newCatName.trim()) return;
    try {
      const { data } = await api.post('/news/categories', { name: newCatName });
      setSelectedCats(prev => [...prev, data.category_id]);
      setNewCatName('');
      onCategoryCreated?.();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[640px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base font-medium">{post ? 'News bearbeiten' : 'News erstellen'}</DialogTitle>
          <DialogDescription className="text-xs text-[#9CA3AF]">
            {isDE ? 'Erstelle eine neue Mitteilung mit Prioritaet, Zielgruppe und optionalem Veroeffentlichungsdatum (Zeitzone: dein lokales Gerät).'
                  : 'Create a news post with priority, target audience and optional publish time (timezone: your local device).'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Titel *" className="border-[#E2E4E0] rounded-xl text-base font-medium" data-testid="news-title-input" />

          <textarea value={content} onChange={e => setContent(e.target.value)} placeholder={isDE ? 'Inhalt (Markdown unterstuetzt)...' : 'Content (Markdown supported)...'}
            className="w-full min-h-[120px] p-3 border border-[#E2E4E0] rounded-xl text-sm resize-y focus:outline-none focus:border-[#4A5D4E]" data-testid="news-content-input" />

          <Input value={excerpt} onChange={e => setExcerpt(e.target.value)} placeholder={isDE ? 'Kurzbeschreibung (optional)' : 'Short description (optional)'}
            className="border-[#E2E4E0] rounded-xl text-sm" />

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F4F1] rounded-lg text-xs cursor-pointer hover:bg-[#E2E4E0] transition-colors">
              <Upload className="w-3.5 h-3.5" />{isDE ? 'Datei hochladen' : 'Upload file'}
              <input type="file" className="hidden" onChange={handleFileUpload} />
            </label>
            {coverImage && <span className="text-[10px] text-[#6B8E23] flex items-center gap-1"><Image className="w-3 h-3" />{t('coverImageSet')}</span>}
            {attachments.length > 0 && <span className="text-[10px] text-[#9CA3AF]">{attachments.length} {t('attachmentsCount')}</span>}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{isDE ? 'Prioritaet' : 'Priority'}</label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger className="h-8 text-xs border-[#E2E4E0] rounded-lg"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="important">Wichtig</SelectItem>
                  <SelectItem value="critical">Kritisch</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Switch checked={pinned} onCheckedChange={setPinned} data-testid="switch-pinned" />
              <label className="text-xs text-[#6B7280]">Angepinnt</label>
            </div>
            <div className="flex items-end gap-2">
              <Switch checked={isMandatory} onCheckedChange={setIsMandatory} data-testid="switch-mandatory" />
              <label className="text-xs text-[#6B7280]">Pflicht</label>
            </div>
            <div className="flex items-end gap-2">
              <Switch checked={commentsEnabled} onCheckedChange={setCommentsEnabled} data-testid="switch-comments" />
              <label className="text-xs text-[#6B7280]">{isDE ? 'Kommentare' : 'Comments'}</label>
            </div>
          </div>

          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Kategorien</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {categories.map(cat => (
                <button key={cat.category_id} onClick={() => setSelectedCats(prev => prev.includes(cat.category_id) ? prev.filter(c => c !== cat.category_id) : [...prev, cat.category_id])}
                  className={`text-[11px] px-2 py-0.5 rounded-full transition-colors ${selectedCats.includes(cat.category_id) ? 'text-white' : ''}`}
                  style={selectedCats.includes(cat.category_id) ? { backgroundColor: cat.color } : { backgroundColor: `${cat.color}15`, color: cat.color }}>
                  {cat.name}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              <Input value={newCatName} onChange={e => setNewCatName(e.target.value)} placeholder="Neue Kategorie..." className="h-7 text-xs border-[#E2E4E0] rounded-lg flex-1" />
              <Button size="sm" variant="outline" onClick={createCategory} className="h-7 text-xs rounded-lg border-[#E2E4E0]"><Plus className="w-3 h-3" /></Button>
            </div>
          </div>

          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Tags</label>
            <Input value={tags} onChange={e => setTags(e.target.value)} placeholder="Tag1, Tag2, Tag3" className="border-[#E2E4E0] rounded-xl text-xs" />
          </div>

          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1.5">{t('targetAudience')}</label>
            <AudiencePicker
              targetAll={targetAll}
              onTargetAllChange={setTargetAll}
              targetGroups={targetGroups}
              onTargetGroupsChange={setTargetGroups}
              targetUserIds={targetUserIds}
              onTargetUserIdsChange={setTargetUserIds}
              groups={groups}
              isDE={isDE}
            />
            {!targetAll && (
              <div className="grid grid-cols-2 gap-2 mt-3">
                <div>
                  <label className="text-[9px] text-[#9CA3AF] block mb-0.5">{isDE ? 'Zusätzlich: Abteilungen' : 'Also: Departments'}</label>
                  <Input value={targetDepartments} onChange={e => setTargetDepartments(e.target.value)}
                    placeholder="z.B. Innere, Chirurgie" className="h-7 text-[11px] border-[#E2E4E0] rounded"
                    data-testid="target-departments" />
                </div>
                <div>
                  <label className="text-[9px] text-[#9CA3AF] block mb-0.5">{isDE ? 'Zusätzlich: Standorte' : 'Also: Locations'}</label>
                  <Input value={targetLocations} onChange={e => setTargetLocations(e.target.value)}
                    placeholder="z.B. Nord, Sued" className="h-7 text-[11px] border-[#E2E4E0] rounded"
                    data-testid="target-locations" />
                </div>
                <div>
                  <label className="text-[9px] text-[#9CA3AF] block mb-0.5">{t('professions')}</label>
                  <Input value={targetProfessions} onChange={e => setTargetProfessions(e.target.value)}
                    placeholder="z.B. Pflege, Arzt" className="h-7 text-[11px] border-[#E2E4E0] rounded"
                    data-testid="target-professions" />
                </div>
                <div>
                  <label className="text-[9px] text-[#9CA3AF] block mb-0.5">{t('roles')}</label>
                  <div className="flex flex-wrap gap-1">
                    {['admin', 'redakteur', 'freigeber', 'autor', 'member'].map(r => (
                      <button key={r} type="button" onClick={() => setTargetRoles(prev => prev.includes(r) ? prev.filter(x => x !== r) : [...prev, r])}
                        className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${targetRoles.includes(r) ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280]'}`}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Video + External Link */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{isDE ? 'Video-URL (YouTube/Vimeo)' : 'Video URL'}</label>
              <Input value={videoUrl} onChange={e => setVideoUrl(e.target.value)} placeholder="https://..."
                className="border-[#E2E4E0] rounded-xl text-xs h-8" data-testid="news-video-url" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{isDE ? 'Externer Link' : 'External Link'}</label>
              <Input value={externalLink} onChange={e => setExternalLink(e.target.value)} placeholder="https://..."
                className="border-[#E2E4E0] rounded-xl text-xs h-8" data-testid="news-external-link" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{isDE ? 'Veroeffentlichen am' : 'Publish at'}</label>
              <Input type="datetime-local" value={isoToLocalInput(publishAt)}
                onChange={e => setPublishAt(localInputToIso(e.target.value))}
                className="h-8 text-xs border-[#E2E4E0] rounded-lg" data-testid="news-publish-at" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">{isDE ? 'Ablaufdatum' : 'Expires at'}</label>
              <Input type="datetime-local" value={isoToLocalInput(expiresAt)}
                onChange={e => setExpiresAt(localInputToIso(e.target.value))}
                className="h-8 text-xs border-[#E2E4E0] rounded-lg" data-testid="news-expires-at" />
            </div>
          </div>

          {/* Governance: Distribution Channels + Page Owner */}
          <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl p-3 space-y-3">
            <div>
              <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1.5">Kanaele (Multi-Channel-Verteilung)</label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { id: 'intranet', label: 'Intranet', icon: '\uD83C\uDF10' },
                  { id: 'email', label: 'E-Mail', icon: '\u2709\uFE0F' },
                  { id: 'push', label: 'Push', icon: '\uD83D\uDD14' },
                  { id: 'digital_signage', label: 'Bildschirme', icon: '\uD83D\uDCFA' },
                ].map(ch => (
                  <button key={ch.id} type="button"
                    onClick={() => setChannels(prev => prev.includes(ch.id) ? prev.filter(x => x !== ch.id) : [...prev, ch.id])}
                    className={`text-[10px] px-2 py-1 rounded-full transition-colors ${channels.includes(ch.id) ? 'bg-[#4A5D4E] text-white' : 'bg-white text-[#6B7280] border border-[#E2E4E0]'}`}
                    data-testid={`channel-${ch.id}`}>
                    <span className="mr-1">{ch.icon}</span>{ch.label}
                  </button>
                ))}
              </div>
              <p className="text-[9px] text-[#9CA3AF] mt-1.5">{t('channelHint')}</p>
            </div>
            {post?.post_id && (
              <div>
                <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Page Owner (Verantwortlich)</label>
                <div className="flex items-center gap-2 text-xs text-[#4B5563]" data-testid="page-owner-display">
                  <span className="inline-flex items-center gap-1 bg-white border border-[#E2E4E0] rounded-full px-2.5 py-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#6B8E23]"></span>
                    {ownerName || '—'}
                  </span>
                  <span className="text-[10px] text-[#9CA3AF]">Übertragen über das Menü der Newskarte.</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} className="rounded-full border-[#E2E4E0]">{isDE ? 'Abbrechen' : 'Cancel'}</Button>
          {post?.post_id && channels.includes('digital_signage') && (
            <Button
              variant="outline"
              onClick={() => window.open(`/signage?preview=${post.post_id}&theme=dark`, '_blank', 'noopener,noreferrer')}
              className="rounded-full border-[#E2E4E0] text-[#4A5D4E]"
              data-testid="signage-preview-btn"
              title={isDE ? 'In neuem Tab als Bildschirm-Vorschau oeffnen' : 'Open as signage preview in new tab'}
            >
              <Monitor className="w-3.5 h-3.5 mr-1.5" />
              {isDE ? 'Signage-Vorschau' : 'Signage Preview'}
            </Button>
          )}
          <Button variant="outline" onClick={() => handleSave('draft')} disabled={saving} className="rounded-full border-[#E2E4E0]" data-testid="save-draft-btn">
            {isDE ? 'Als Entwurf' : 'Save Draft'}
          </Button>
          <Button onClick={() => handleSave('published')} disabled={saving} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="publish-news-btn">
            {saving ? '...' : (isDE ? 'Veroeffentlichen' : 'Publish')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
