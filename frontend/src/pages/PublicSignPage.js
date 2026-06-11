import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import SignaturePad from '../components/SignaturePad';
import SignaturePlacement from '../components/SignaturePlacement';
import { FileText, Check, AlertCircle, Loader2 } from 'lucide-react';
import api, { API_URL } from '../lib/api';
import { toast } from 'sonner';
import { useLanguage } from '../contexts/LanguageContext';

export default function PublicSignPage() {
  const { t } = useLanguage();
  const { signToken } = useParams();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [signed, setSigned] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [showPad, setShowPad] = useState(false);
  const [placingSignature, setPlacingSignature] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/sign/${signToken}`);
        setDoc(data);
      } catch (err) {
        setError(err.response?.data?.detail || t('documentNotFound'));
      } finally {
        setLoading(false);
      }
    })();
  }, [signToken]);

  const handleSign = (sigData) => {
    setShowPad(false);
    setPlacingSignature(sigData);
  };

  const handlePlacementConfirm = async (finalSigData) => {
    try {
      await api.post(`/sign/${signToken}`, {
        signer_name: signerName,
        signer_email: signerEmail,
        ...finalSigData,
      });
      setPlacingSignature(null);
      setSigned(true);
      toast.success(t('signedAndPlaced'));
    } catch (err) {
      const msg = err.response?.data?.detail || t('signingFailed');
      toast.error(msg);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
        <Loader2 className="w-6 h-6 animate-spin text-[#4A5D4E]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
        <Card className="w-full max-w-md border-[#E2E4E0]">
          <CardContent className="p-8 text-center">
            <AlertCircle className="w-10 h-10 text-[#C87967] mx-auto mb-3" />
            <p className="text-sm text-[#1C1F1D]">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (signed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]" data-testid="sign-success">
        <Card className="w-full max-w-md border-[#E2E4E0]">
          <CardContent className="p-8 text-center">
            <div className="w-14 h-14 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center mx-auto mb-4">
              <Check className="w-7 h-7 text-[#4A5D4E]" />
            </div>
            <h2 className="text-lg font-semibold text-[#1C1F1D] mb-1">{t('signedSuccessfully')}</h2>
            <p className="text-sm text-[#9CA3AF]">{doc?.filename}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Placement overlay
  if (placingSignature && doc) {
    return (
      <SignaturePlacement
        meetingId={doc.meeting_id}
        doc={{ doc_id: doc.doc_id, filename: doc.filename, file_ext: doc.file_ext }}
        signatureData={placingSignature}
        onConfirm={handlePlacementConfirm}
        onCancel={() => { setPlacingSignature(null); setShowPad(true); }}
      />
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F9F8] py-8 px-4" data-testid="public-sign-page">
      <div className="max-w-lg mx-auto space-y-4">
        <div className="text-center mb-6">
          <h1 className="text-xl font-semibold text-[#1C1F1D]">{t('signDocument')}</h1>
          <p className="text-sm text-[#9CA3AF] mt-1">MeetFlow</p>
        </div>

        <Card className="border-[#E2E4E0]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#4A5D4E]" />
              {doc?.filename}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-2">
            {doc?.meeting_title && (
              <p className="text-xs text-[#9CA3AF]">Meeting: {doc.meeting_title}</p>
            )}
            <p className="text-xs text-[#9CA3AF]">{t('uploadedBy')}: {doc?.uploader_name}</p>

            {doc?.signatures?.length > 0 && (
              <div className="pt-2">
                <p className="text-xs font-medium text-[#1C1F1D] mb-1.5">{t('existingSignatures')}:</p>
                <div className="flex flex-wrap gap-1.5">
                  {doc.signatures.map((s, i) => (
                    <Badge key={i} variant="outline" className="text-[10px] border-[#E2E4E0]">
                      <Check className="w-2.5 h-2.5 mr-1 text-[#4A5D4E]" />
                      {s.signer_name} — {new Date(s.signed_at).toLocaleDateString('de-DE')}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {doc?.view_url && (
              <div className="mt-3">
                <Button variant="outline" size="sm" className="text-xs h-7" asChild>
                  <a href={`${API_URL}${doc.view_url}`} target="_blank" rel="noopener noreferrer"
                    data-testid="view-document-link">
                    {t('viewDocument')}
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-[#E2E4E0]">
          <CardContent className="p-5 space-y-4">
            {!showPad ? (
              <>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-[#1C1F1D] mb-1 block">{t('yourName')} *</label>
                    <Input value={signerName} onChange={(e) => setSignerName(e.target.value)}
                      placeholder="Max Mustermann" data-testid="signer-name-input" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-[#1C1F1D] mb-1 block">{t('yourEmail')}</label>
                    <Input value={signerEmail} onChange={(e) => setSignerEmail(e.target.value)}
                      placeholder="max@beispiel.de" type="email" data-testid="signer-email-input" />
                  </div>
                </div>
                <Button onClick={() => setShowPad(true)} disabled={!signerName.trim()}
                  className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-sm"
                  data-testid="proceed-to-sign-btn">
                  {t('proceedToSignature')}
                </Button>
              </>
            ) : (
              <SignaturePad
                signerName={signerName}
                onSign={handleSign}
                onCancel={() => setShowPad(false)}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
