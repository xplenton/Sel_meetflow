import { useState, useEffect } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Disc, FileText, Shield, Check, X, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function ConsentDialog({ consent, meetingId, userId, onResolved, open }) {
  const { t } = useLanguage();
  const [responding, setResponding] = useState(false);
  const [myResponse, setMyResponse] = useState(null);

  useEffect(() => {
    if (open) setMyResponse(null);
  }, [open, consent?.consent_id]);

  if (!open || !consent) return null;

  const isRecording = consent.consent_type === 'recording';
  const Icon = isRecording ? Disc : FileText;
  const alreadyResponded = consent.responses?.[userId]?.status;

  const handleResponse = async (response) => {
    setResponding(true);
    try {
      const { data } = await api.post(`/meetings/${meetingId}/consent/${consent.consent_id}/respond`, { response });
      setMyResponse(response);
      if (data.status === 'approved' || data.status === 'rejected') {
        onResolved?.(data.status);
      }
    } catch (err) {
      console.error('Consent response failed:', err);
    } finally { setResponding(false); }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center" data-testid="consent-dialog-overlay">
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-[420px] mx-4 overflow-hidden animate-fade-in" data-testid="consent-dialog">
        {/* Header */}
        <div className={`px-6 py-4 ${isRecording ? 'bg-[#E25C5C]/10' : 'bg-[#4A5D4E]/10'}`}>
          <div className="flex items-center gap-3">
            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isRecording ? 'bg-[#E25C5C]/20' : 'bg-[#4A5D4E]/20'}`}>
              <Icon className={`w-6 h-6 ${isRecording ? 'text-[#E25C5C]' : 'text-[#4A5D4E]'}`} />
            </div>
            <div>
              <h2 className="text-base font-medium text-[#1C1F1D]">
                {isRecording ? 'Recording Consent Required' : 'Transcript Consent Required'}
              </h2>
              <p className="text-sm text-[#6B7280] mt-0.5">
                {consent.requested_by} wants to start {isRecording ? 'recording' : 'transcribing'}
              </p>
            </div>
          </div>
        </div>

        <div className="px-6 py-4">
          {/* Privacy notice */}
          <div className="flex items-start gap-3 p-3 bg-[#F3F4F1] rounded-xl mb-4">
            <Shield className="w-4 h-4 text-[#4A5D4E] mt-0.5 flex-shrink-0" />
            <p className="text-xs text-[#4B5563] leading-relaxed">
              {isRecording
                ? 'This meeting will be recorded. The recording will be available to participants after the meeting ends. Your video, audio, and screen sharing will be captured.'
                : 'This meeting will be transcribed. Chat messages and spoken content will be captured as text. The transcript will be available to participants after the meeting.'}
            </p>
          </div>

          {/* Response area */}
          {myResponse || alreadyResponded ? (
            <div className="text-center py-3">
              <Badge className={`text-xs px-3 py-1 ${
                (myResponse || alreadyResponded) === 'accepted'
                  ? 'bg-[#6B8E23]/10 text-[#6B8E23]'
                  : 'bg-[#C87967]/10 text-[#C87967]'
              }`}>
                {(myResponse || alreadyResponded) === 'accepted' ? (
                  <><Check className="w-3.5 h-3.5 mr-1" /> You accepted</>
                ) : (
                  <><X className="w-3.5 h-3.5 mr-1" /> You declined</>
                )}
              </Badge>
              <p className="text-xs text-[#9CA3AF] mt-2">Waiting for other participants...</p>
            </div>
          ) : (
            <div className="flex gap-3">
              <Button onClick={() => handleResponse('declined')} disabled={responding}
                variant="outline" className="flex-1 rounded-full border-[#C87967] text-[#C87967] hover:bg-[#C87967]/10 h-11"
                data-testid="consent-decline-button">
                <X className="w-4 h-4 mr-1.5" /> Decline
              </Button>
              <Button onClick={() => handleResponse('accepted')} disabled={responding}
                className="flex-1 rounded-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-11"
                data-testid="consent-accept-button">
                {responding ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Check className="w-4 h-4 mr-1.5" />}
                I Consent
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
