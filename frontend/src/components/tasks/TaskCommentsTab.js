import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { Trash2, X, Send } from 'lucide-react';
import { sanitizeHTML } from '../../lib/sanitize';

/**
 * TaskCommentsTab — threaded comments tab with @-mention picker.
 * Extracted from TaskDetailDialog (iter 216).
 *
 * Note: comment threading is rendered via a render helper (not a recursive
 * React component) to keep the JSX tree easy for the Babel traversal pass.
 */
function renderCommentNode(c, depth, ctx) {
  const replies = ctx.comments.filter(rc => rc.parent_id === c.comment_id);
  const author = ctx.userMap[c.author_id];
  const safeHtml = sanitizeHTML((c.content || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/@\[([^\]]+)\]\(([^)]+)\)/g, '<span class="bg-[#4A5D4E]/10 text-[#4A5D4E] px-1 py-0.5 rounded text-xs font-medium">@$1</span>'));
  return (
    <div key={c.comment_id} className={`${depth ? 'ml-6 border-l-2 border-[#E2E4E0] pl-3' : ''} mb-3`} data-testid={`comment-${c.comment_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-xs text-[#6B7280] mb-1">
            <span className="font-medium text-[#1C1F1D]">{author?.name || c.author_name}</span>
            <span>·</span>
            <span>{new Date(c.created_at).toLocaleString('de-DE')}</span>
            {c.edited_at && <span className="italic">(bearb.)</span>}
          </div>
          <div className="text-sm text-[#1C1F1D] whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html: safeHtml }} />
        </div>
        <button onClick={() => ctx.onDelete(c.comment_id)} className="text-[#9CA3AF] hover:text-[#C87967] text-xs">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <button onClick={() => ctx.onReply(c.comment_id)}
        data-testid={`reply-${c.comment_id}`}
        className="text-[10px] text-[#4A5D4E] hover:underline mt-1">
        Antworten
      </button>
      {replies.map(r => renderCommentNode(r, depth + 1, ctx))}
    </div>
  );
}

export default function TaskCommentsTab({
  comments, users, userMap,
  draftCmt, onDraftChange,
  replyTo, onSetReplyTo,
  onDeleteComment, onSubmitComment, onInsertMention,
}) {
  const tree = comments.filter(c => !c.parent_id);
  const ctx = { comments, userMap, onDelete: onDeleteComment, onReply: onSetReplyTo };

  return (
    <div data-testid="task-comments-section">
      {comments.length === 0 ? (
        <p className="text-xs text-[#9CA3AF] text-center py-3">Noch keine Kommentare.</p>
      ) : (
        <div>{tree.map(c => renderCommentNode(c, 0, ctx))}</div>
      )}
      <div className="mt-3 border-t border-[#E2E4E0] pt-3">
        {replyTo && (
          <div className="text-[11px] text-[#6B7280] mb-1 flex items-center gap-2">
            Antwort auf Kommentar
            <button onClick={() => onSetReplyTo(null)} className="text-[#C87967]">
              <X className="w-3 h-3" />
            </button>
          </div>
        )}
        <Textarea
          data-testid="task-comment-input"
          value={draftCmt} onChange={e => onDraftChange(e.target.value)}
          placeholder="Kommentar schreiben - tippe @ für Erwaehnung"
          rows={2}
          className="text-sm border-[#E2E4E0] rounded-lg"
        />
        <div className="flex items-center justify-between mt-1.5">
          <select data-testid="task-mention-select" value=""
            onChange={(e) => { if (e.target.value) { onInsertMention(JSON.parse(e.target.value)); e.target.value = ''; } }}
            className="text-xs h-8 px-2 border border-[#E2E4E0] rounded-md bg-white">
            <option value="">@ Mention ...</option>
            {users.map(u => <option key={u.user_id} value={JSON.stringify(u)}>{u.name || u.email}</option>)}
          </select>
          <Button data-testid="task-comment-submit" size="sm" onClick={onSubmitComment} disabled={!draftCmt.trim()}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-8 text-xs">
            <Send className="w-3 h-3 mr-1" /> Senden
          </Button>
        </div>
      </div>
    </div>
  );
}
