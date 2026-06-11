import { useState, useEffect, useCallback, useRef } from 'react';
import { flushSync } from 'react-dom';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import SignaturePad from './SignaturePad';
import SignaturePlacement from './SignaturePlacement';
import SignatureFieldsPanel from './SignatureFieldsPanel';
import DocThumbnail from './DocThumbnail';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  X, Upload, FileText, Download, Presentation, PenTool, Send,
  GripVertical, Trash2, Image, File as FileIcon, Check, History, FileDown
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
function SortableDocItem({
  doc, meetingId, isHost, userId, userName, presentedDoc, participants,
  isImageFn, getIconFn, onDownload, onDownloadSigned, onPresent, onSign,
  onRequestSig, onEmail, onAudit, onDelete, onFieldSign
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: doc.doc_id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : 'auto',
  };
  const Icon = getIconFn(doc.file_ext);
  const isPresenting = presentedDoc?.doc_id === doc.doc_id;
  const sigCount = doc.signatures?.length || 0;
  const canDelete = isHost || doc.uploaded_by === userId;

  return (
    <div ref={setNodeRef} style={style}
      className={`p-2.5 rounded-lg border transition-colors ${
        isPresenting ? 'border-[#4A5D4E] bg-[#4A5D4E]/5' : 'border-[#E2E4E0] hover:border-[#4A5D4E]/30'
      } ${isDragging ? 'shadow-lg' : ''}`}
      data-testid={`doc-${doc.doc_id}`}>
      {/* Thumbnail Preview */}
      {(doc.file_ext === 'pdf' || isImageFn(doc.file_ext)) && (
        <div className="w-full h-20 rounded-md overflow-hidden mb-2 border border-[#E2E4E0] bg-[#F9F9F8]"
          data-testid={`doc-thumbnail-container-${doc.doc_id}`}>
          <DocThumbnail meetingId={meetingId} docId={doc.doc_id} fileExt={doc.file_ext} filename={doc.filename} />
        </div>
      )}
      <div className="flex items-center gap-2">
        {isHost && (
          <button {...attributes} {...listeners}
            className="p-0.5 rounded cursor-grab active:cursor-grabbing text-[#9CA3AF] hover:text-[#4A5D4E] flex-shrink-0 touch-none"
            data-testid={`drag-handle-${doc.doc_id}`}>
            <GripVertical className="w-3.5 h-3.5" />
          </button>
        )}
        <div className="w-8 h-8 rounded-lg bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-[#4A5D4E]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-[#1C1F1D] truncate">{doc.filename}</p>
          <p className="text-[10px] text-[#9CA3AF]">
            {doc.uploader_name} {sigCount > 0 && `- ${sigCount} Unterschrift${sigCount > 1 ? 'en' : ''}`}
          </p>
        </div>
        {isPresenting && <Badge className="bg-[#4A5D4E] text-white text-[9px] flex-shrink-0">Live</Badge>}
        {doc.requires_signature && <Badge className="bg-[#D4A373]/20 text-[#D4A373] text-[9px] flex-shrink-0">Signatur</Badge>}
      </div>

      <div className="flex gap-0.5 mt-2 flex-wrap">
        <Button variant="ghost" size="sm" onClick={() => onDownload(doc)} title="Herunterladen"
          className="h-6 w-6 p-0 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid={`download-doc-${doc.doc_id}`}>
          <Download className="w-3 h-3" />
        </Button>
        {sigCount > 0 && (
          <Button variant="ghost" size="sm" onClick={() => onDownloadSigned(doc)} title="Signierte Version"
            className="h-6 w-6 p-0 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid={`download-signed-${doc.doc_id}`}>
            <FileDown className="w-3 h-3" />
          </Button>
        )}
        {isHost && (
          <Button variant="ghost" size="sm" onClick={() => onPresent(doc)} title={isPresenting ? 'Stopp' : 'Präsentieren'}
            className={`h-6 w-6 p-0 hover:bg-[#4A5D4E]/10 ${isPresenting ? 'text-[#C87967]' : 'text-[#4A5D4E]'}`}
            data-testid={`present-doc-${doc.doc_id}`}>
            <Presentation className="w-3 h-3" />
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => onSign(doc)} title="Signieren"
          className="h-6 w-6 p-0 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid={`sign-doc-${doc.doc_id}`}>
          <PenTool className="w-3 h-3" />
        </Button>
        {isHost && (
          <>
            <Button variant="ghost" size="sm" onClick={() => onRequestSig(doc)} title="Signatur anfordern"
              className="h-6 w-6 p-0 text-[#D4A373] hover:bg-[#D4A373]/10" data-testid={`request-sig-${doc.doc_id}`}>
              <Check className="w-3 h-3" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onEmail(doc)} title={t('sendViaEmail')}
              className="h-6 w-6 p-0 text-[#4A5D4E] hover:bg-[#4A5D4E]/10" data-testid={`email-doc-${doc.doc_id}`}>
              <Send className="w-3 h-3" />
            </Button>
          </>
        )}
        <Button variant="ghost" size="sm" onClick={() => onAudit(doc)} title="Audit-Verlauf"
          className="h-6 w-6 p-0 text-[#6B7280] hover:bg-gray-100" data-testid={`audit-doc-${doc.doc_id}`}>
          <History className="w-3 h-3" />
        </Button>
        {canDelete && (
          <Button variant="ghost" size="sm" onClick={() => onDelete(doc)} title="Löschen"
            className="h-6 w-6 p-0 text-[#C87967] hover:text-red-700 hover:bg-red-50"
            data-testid={`delete-doc-${doc.doc_id}`}>
            <Trash2 className="w-3 h-3" />
          </Button>
        )}
      </div>

      {/* Signature Fields - collapsible */}
      <details className="mt-2 pt-2 border-t border-[#E2E4E0]">
        <summary className="text-[10px] text-[#9CA3AF] cursor-pointer hover:text-[#4A5D4E] select-none">
          Signaturfelder
        </summary>
        <div className="mt-1">
          <SignatureFieldsPanel
            meetingId={meetingId} docId={doc.doc_id}
            isHost={isHost} userId={userId} userName={userName}
            participants={participants || []}
            onSignField={(sigData) => onFieldSign(doc, sigData)}
          />
        </div>
      </details>
    </div>
  );
}

export default function DocumentPanel({
  meetingId, isHost, userId, userName, onClose,
  presentedDoc, onPresentDoc, wsRef, participants
}) {
  const { t } = useLanguage();
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [signDialogOpen, setSignDialogOpen] = useState(false);
  const [signingDoc, setSigningDoc] = useState(null);
  const [emailDialogOpen, setEmailDialogOpen] = useState(false);
  const [emailDoc, setEmailDoc] = useState(null);
  const [emails, setEmails] = useState('');
  const [sendingEmails, setSendingEmails] = useState(false);
  const [auditDialogOpen, setAuditDialogOpen] = useState(false);
  const [auditDoc, setAuditDoc] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [placingSignature, setPlacingSignature] = useState(null); // {doc, sigData}
  const inputRef = useRef(null);

  const fetchDocs = useCallback(async () => {
    try {
      const { data } = await api.get(`/meetings/${meetingId}/documents`);
      setDocs(data);
    } catch {}
  }, [meetingId]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { toast.error('Max 50MB'); return; }
    const ext = file.name.split('.').pop().toLowerCase();
    const allowed = ['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'webp'];
    if (!allowed.includes(ext)) {
      toast.error(`Erlaubt: ${allowed.join(', ')}`);
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await api.post(`/meetings/${meetingId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success('Dokument hochgeladen');
      fetchDocs();
    } catch (err) {
      toast.error('Upload fehlgeschlagen');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const handleDownload = async (doc) => {
    try {
      const hasSigs = doc.signatures?.length > 0;
      const endpoint = hasSigs
        ? `/meetings/${meetingId}/documents/${doc.doc_id}/download-signed`
        : `/meetings/${meetingId}/documents/${doc.doc_id}/view`;
      const response = await api.get(endpoint, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = hasSigs ? `signed_${doc.filename}` : doc.filename;
      a.click();
      URL.revokeObjectURL(url);
      if (hasSigs) toast.success('Signiertes Dokument heruntergeladen');
    } catch {
      toast.error('Download fehlgeschlagen');
    }
  };

  const handleDownloadSigned = async (doc) => {
    try {
      const response = await api.get(
        `/meetings/${meetingId}/documents/${doc.doc_id}/download-signed`,
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `signed_${doc.filename}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Signiertes Dokument heruntergeladen');
    } catch {
      toast.error('Download fehlgeschlagen');
    }
  };

  const handlePresent = async (doc) => {
    try {
      const nowPresenting = presentedDoc?.doc_id === doc.doc_id;
      await api.post(`/meetings/${meetingId}/documents/${doc.doc_id}/present`, {
        presenting: !nowPresenting,
        page: 1,
      });
      if (nowPresenting) {
        onPresentDoc(null);
      } else {
        onPresentDoc({ ...doc, current_page: 1 });
      }
      fetchDocs();
    } catch {
      toast.error('Fehler beim Präsentieren');
    }
  };

  const handleRequestSignatures = async (doc) => {
    try {
      await api.post(`/meetings/${meetingId}/documents/${doc.doc_id}/request-signatures`);
      toast.success('Unterschrifts-Anfrage gesendet');
      fetchDocs();
    } catch {
      toast.error('Fehler beim Anfordern');
    }
  };

  const openSignDialog = (doc) => {
    setSigningDoc(doc);
    setSignDialogOpen(true);
  };

  const handleSign = async (sigData) => {
    if (!signingDoc) return;
    const doc = signingDoc;
    // Close dialog first with flushSync to let React finish DOM cleanup
    flushSync(() => {
      setSignDialogOpen(false);
      setSigningDoc(null);
    });
    // Open placement after dialog is fully unmounted
    setTimeout(() => {
      setPlacingSignature({ doc, sigData });
    }, 50);
  };

  const handlePlacementConfirm = async (finalSigData) => {
    const doc = placingSignature?.doc;
    if (!doc) return;
    try {
      await api.post(`/meetings/${meetingId}/documents/${doc.doc_id}/sign`, finalSigData);
      flushSync(() => { setPlacingSignature(null); });
      setTimeout(() => { toast.success('Unterschrift platziert und gespeichert'); }, 50);
      fetchDocs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern');
    }
  };

  const handleFieldSign = async (doc, sigData) => {
    try {
      await api.post(`/meetings/${meetingId}/documents/${doc.doc_id}/sign`, sigData);
      setTimeout(() => { toast.success('Signaturfeld unterschrieben'); }, 50);
      fetchDocs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Unterschreiben');
    }
  };

  const openEmailDialog = (doc) => {
    setEmailDoc(doc);
    setEmails('');
    setEmailDialogOpen(true);
  };

  const handleSendForSigning = async () => {
    if (!emailDoc || !emails.trim()) return;
    setSendingEmails(true);
    try {
      const emailList = emails.split(',').map(e => e.trim()).filter(Boolean);
      const { data } = await api.post(
        `/meetings/${meetingId}/documents/${emailDoc.doc_id}/send-for-signing`,
        { emails: emailList }
      );
      const sent = data.sent;
      flushSync(() => { setEmailDialogOpen(false); });
      setTimeout(() => { toast.success(`Signatur-Link an ${sent} Empfänger gesendet`); }, 50);
      fetchDocs();
    } catch {
      toast.error('Versand fehlgeschlagen');
    } finally {
      setSendingEmails(false);
    }
  };

  const isImage = (ext) => ['png', 'jpg', 'jpeg', 'webp'].includes(ext);
  const getIcon = (ext) => isImage(ext) ? Image : FileIcon;

  const actionLabels = {
    uploaded: 'Hochgeladen',
    viewed: 'Angesehen',
    presented: 'Präsentiert',
    presentation_stopped: 'Präsentation beendet',
    signed: 'Unterschrieben (Live)',
    signed_async: 'Unterschrieben (Async)',
    signature_requested: 'Unterschrift angefordert',
    sent_for_signing: 'Zum Unterschreiben versendet',
  };

  const openAuditLog = async (doc) => {
    setAuditDoc(doc);
    setAuditDialogOpen(true);
    setAuditLoading(true);
    try {
      const { data } = await api.get(`/meetings/${meetingId}/documents/${doc.doc_id}/audit-log`);
      setAuditLogs(data);
    } catch {
      toast.error('Verlauf konnte nicht geladen werden');
      setAuditLogs([]);
    } finally {
      setAuditLoading(false);
    }
  };

  const handleExportAuditPdf = async () => {
    if (!auditDoc) return;
    try {
      const response = await api.get(
        `/meetings/${meetingId}/documents/${auditDoc.doc_id}/audit-log/pdf`,
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_trail_${auditDoc.doc_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Audit-Trail PDF heruntergeladen');
    } catch {
      toast.error('PDF-Export fehlgeschlagen');
    }
  };

  const handleDelete = async (doc) => {
    if (!window.confirm(`"${doc.filename}" wirklich löschen?`)) return;
    try {
      await api.delete(`/meetings/${meetingId}/documents/${doc.doc_id}`);
      if (presentedDoc?.doc_id === doc.doc_id) onPresentDoc(null);
      toast.success('Dokument gelöscht');
      fetchDocs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = docs.findIndex(d => d.doc_id === active.id);
    const newIndex = docs.findIndex(d => d.doc_id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    const newDocs = arrayMove(docs, oldIndex, newIndex);
    setDocs(newDocs);
    try {
      await api.put(`/meetings/${meetingId}/documents/reorder`, {
        doc_ids: newDocs.map(d => d.doc_id)
      });
    } catch {
      toast.error('Reihenfolge konnte nicht gespeichert werden');
      fetchDocs();
    }
  };

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="document-panel">
      <div className="flex items-center justify-between p-4 border-b border-[#E2E4E0]">
        <h3 className="text-sm font-medium text-[#1C1F1D]">Dokumente</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]"
          data-testid="close-document-panel">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3 border-b border-[#E2E4E0]">
        <input ref={inputRef} type="file" onChange={handleUpload} className="hidden"
          accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp" data-testid="document-file-input" />
        <Button onClick={() => inputRef.current?.click()} disabled={uploading} size="sm"
          className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg text-xs h-8"
          data-testid="upload-document-btn">
          <Upload className="w-3.5 h-3.5 mr-1.5" />
          {uploading ? 'Wird hochgeladen...' : 'Dokument hochladen'}
        </Button>
      </div>

      <ScrollArea className="flex-1 p-3">
        {docs.length === 0 ? (
          <div className="text-center py-8">
            <FileText className="w-8 h-8 text-[#E2E4E0] mx-auto mb-2" />
            <p className="text-xs text-[#9CA3AF]">{t('noDocuments')}</p>
          </div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={docs.map(d => d.doc_id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-2">
                {docs.map(doc => (
                  <SortableDocItem
                    key={doc.doc_id}
                    doc={doc}
                    meetingId={meetingId}
                    isHost={isHost}
                    userId={userId}
                    userName={userName}
                    presentedDoc={presentedDoc}
                    participants={participants}
                    isImageFn={isImage}
                    getIconFn={getIcon}
                    onDownload={handleDownload}
                    onDownloadSigned={handleDownloadSigned}
                    onPresent={handlePresent}
                    onSign={openSignDialog}
                    onRequestSig={handleRequestSignatures}
                    onEmail={openEmailDialog}
                    onAudit={openAuditLog}
                    onDelete={handleDelete}
                    onFieldSign={handleFieldSign}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </ScrollArea>

      {/* Sign Dialog */}
      <Dialog open={signDialogOpen} onOpenChange={setSignDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="sign-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">{t('signDocument')}</DialogTitle>
            <DialogDescription className="text-xs text-[#9CA3AF]">
              {signingDoc?.filename}
            </DialogDescription>
          </DialogHeader>
          <SignaturePad
            signerName={userName}
            onSign={handleSign}
            onCancel={() => { setSignDialogOpen(false); setSigningDoc(null); }}
          />
        </DialogContent>
      </Dialog>

      {/* Email Dialog */}
      <Dialog open={emailDialogOpen} onOpenChange={setEmailDialogOpen}>
        <DialogContent className="sm:max-w-md" data-testid="email-sign-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">{t('sendForSigning')}</DialogTitle>
            <DialogDescription className="text-xs text-[#9CA3AF]">
              {emailDoc?.filename} — E-Mail-Adressen eingeben (kommagetrennt)
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              value={emails}
              onChange={(e) => setEmails(e.target.value)}
              placeholder="email@beispiel.de, email2@beispiel.de"
              data-testid="email-recipients-input"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setEmailDialogOpen(false)}
                className="text-xs h-8">Abbrechen</Button>
              <Button size="sm" onClick={handleSendForSigning} disabled={sendingEmails || !emails.trim()}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs h-8" data-testid="send-signing-email-btn">
                <Send className="w-3.5 h-3.5 mr-1" />
                {sendingEmails ? 'Wird gesendet...' : 'Senden'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Audit Trail Dialog */}
      <Dialog open={auditDialogOpen} onOpenChange={setAuditDialogOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col" data-testid="audit-trail-dialog">
          <DialogHeader>
            <DialogTitle className="text-base flex items-center gap-2">
              <History className="w-4 h-4 text-[#4A5D4E]" />Dokumenten-Verlauf
            </DialogTitle>
            <DialogDescription className="text-xs text-[#9CA3AF] flex items-center justify-between">
              <span>{auditDoc?.filename}</span>
              <Button variant="outline" size="sm" onClick={handleExportAuditPdf}
                disabled={auditLoading || auditLogs.length === 0}
                className="text-[10px] h-6 px-2 ml-2" data-testid="export-audit-pdf-btn">
                <FileDown className="w-3 h-3 mr-1" />PDF Export
              </Button>
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="flex-1 max-h-[50vh] pr-2">
            {auditLoading ? (
              <div className="text-center py-8 text-xs text-[#9CA3AF]">Wird geladen...</div>
            ) : auditLogs.length === 0 ? (
              <div className="text-center py-8 text-xs text-[#9CA3AF]">{t('noEntries')}</div>
            ) : (
              <div className="space-y-1.5">
                {auditLogs.map((log, i) => (
                  <div key={log.log_id || i}
                    className="flex items-start gap-3 p-2.5 rounded-lg border border-[#E2E4E0] hover:bg-[#F9F9F8] transition-colors"
                    data-testid={`audit-entry-${i}`}>
                    <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <History className="w-3 h-3 text-[#4A5D4E]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-[#1C1F1D]">
                          {actionLabels[log.action] || log.action}
                        </span>
                        <Badge variant="outline" className="text-[9px] border-[#E2E4E0] px-1.5">
                          {log.action}
                        </Badge>
                      </div>
                      <p className="text-[10px] text-[#6B7280] mt-0.5">
                        {log.user_name || log.user_email || 'Anonym'}
                        {log.ip && <span className="ml-1 text-[#9CA3AF]">({log.ip})</span>}
                      </p>
                      {log.details && (
                        <p className="text-[10px] text-[#9CA3AF] mt-0.5 truncate">{log.details}</p>
                      )}
                      <p className="text-[9px] text-[#9CA3AF] mt-1">
                        {new Date(log.timestamp).toLocaleString('de-DE', {
                          day: '2-digit', month: '2-digit', year: 'numeric',
                          hour: '2-digit', minute: '2-digit', second: '2-digit'
                        })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Signature Placement Overlay */}
      {placingSignature && (
        <SignaturePlacement
          meetingId={meetingId}
          doc={placingSignature.doc}
          signatureData={placingSignature.sigData}
          onConfirm={handlePlacementConfirm}
          onCancel={() => setPlacingSignature(null)}
        />
      )}
    </div>
  );
}
