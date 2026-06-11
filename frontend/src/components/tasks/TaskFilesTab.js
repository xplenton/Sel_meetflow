import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Paperclip, Link2, Trash2 } from 'lucide-react';

/**
 * TaskFilesTab — attachments tab: file upload + URL link form + list of
 * attachments (image thumbnails for images, generic icon otherwise).
 * Extracted from TaskDetailDialog (iter 216).
 */
export default function TaskFilesTab({
  attachments,
  showLinkForm, onToggleLinkForm,
  linkUrl, onLinkUrlChange, linkName, onLinkNameChange,
  onFile, onAddLink, onRemoveAttachment,
}) {
  return (
    <div data-testid="task-attachments-section">
      <div className="flex gap-2 mb-3 flex-wrap">
        <label className="cursor-pointer">
          <input type="file" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} data-testid="task-file-input" />
          <span className="inline-flex items-center px-3 py-1.5 bg-[#4A5D4E] text-white text-xs rounded-lg hover:bg-[#3E4E42]">
            <Paperclip className="w-3 h-3 mr-1" />Datei
          </span>
        </label>
        <Button size="sm" variant="outline" onClick={onToggleLinkForm}
          data-testid="task-add-link" className="h-8 text-xs">
          <Link2 className="w-3 h-3 mr-1" />Link
        </Button>
      </div>
      {showLinkForm && (
        <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-lg p-2 mb-3 space-y-1.5">
          <Input data-testid="task-link-url" value={linkUrl} onChange={e => onLinkUrlChange(e.target.value)}
            placeholder="https://..." className="h-8 border-[#E2E4E0] text-xs" autoFocus />
          <Input data-testid="task-link-name" value={linkName} onChange={e => onLinkNameChange(e.target.value)}
            placeholder="Anzeigename (optional)" className="h-8 border-[#E2E4E0] text-xs" />
          <div className="flex gap-1.5 justify-end">
            <Button size="sm" variant="outline"
              onClick={() => { onToggleLinkForm(); onLinkUrlChange(''); onLinkNameChange(''); }}
              className="h-7 text-xs">Abbrechen</Button>
            <Button size="sm" data-testid="task-link-submit" onClick={onAddLink}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-7 text-xs">Hinzufügen</Button>
          </div>
        </div>
      )}
      {attachments.length === 0 ? (
        <p className="text-xs text-[#9CA3AF] text-center py-3">Keine Anhänge.</p>
      ) : (
        <div className="space-y-1.5">
          {attachments.map(a => {
            const isImg = a.kind === 'file' && (a.mime || '').startsWith('image/');
            const url = a.kind === 'file' ? `/api/tasks/files/${a.file_id}` : a.url;
            return (
              <div key={a.attachment_id} className="flex items-center gap-2 bg-[#F9F9F8] rounded-lg p-2">
                {isImg ? (
                  <img src={url} alt={a.name} className="w-12 h-12 rounded object-cover" />
                ) : (
                  <div className="w-12 h-12 rounded bg-[#E2E4E0] flex items-center justify-center">
                    {a.kind === 'link' ? <Link2 className="w-5 h-5 text-[#4A5D4E]" /> : <Paperclip className="w-5 h-5 text-[#4A5D4E]" />}
                  </div>
                )}
                <a href={url} target="_blank" rel="noopener noreferrer"
                  className="flex-1 text-sm text-[#1C1F1D] hover:underline truncate">{a.name}</a>
                <button onClick={() => onRemoveAttachment(a.attachment_id)}
                  className="text-[#9CA3AF] hover:text-[#C87967]"><Trash2 className="w-3 h-3" /></button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
