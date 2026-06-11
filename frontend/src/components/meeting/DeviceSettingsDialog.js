import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * Device-Settings dialog for switching the active camera and microphone
 * during a live meeting. Extracted from LiveMeetingPage (iter 215 refactor).
 */
export default function DeviceSettingsDialog({
  open, onOpenChange,
  devices, selectedVideoDevice, selectedAudioDevice,
  onSwitchCamera, onSwitchMic,
}) {
  const { t } = useLanguage();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Geräteeinstellungen</DialogTitle>
          <DialogDescription>{t('pickCameraAndMic')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div>
            <label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Kamera</label>
            <Select value={selectedVideoDevice} onValueChange={onSwitchCamera}>
              <SelectTrigger className="border-[#E2E4E0] rounded-xl text-xs" data-testid="live-camera-select">
                <SelectValue placeholder={devices.video.length === 0 ? 'Keine Kamera gefunden' : 'Kamera wählen'} />
              </SelectTrigger>
              <SelectContent>
                {devices.video.map((d, i) => (
                  <SelectItem key={d.deviceId || `cam-${i}`} value={d.deviceId || `cam-${i}`} className="text-xs">
                    {d.label || `Kamera ${i + 1}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Mikrofon</label>
            <Select value={selectedAudioDevice} onValueChange={onSwitchMic}>
              <SelectTrigger className="border-[#E2E4E0] rounded-xl text-xs" data-testid="live-mic-select">
                <SelectValue placeholder={devices.audio.length === 0 ? 'Kein Mikrofon gefunden' : 'Mikrofon wählen'} />
              </SelectTrigger>
              <SelectContent>
                {devices.audio.map((d, i) => (
                  <SelectItem key={d.deviceId || `mic-${i}`} value={d.deviceId || `mic-${i}`} className="text-xs">
                    {d.label || `Mikrofon ${i + 1}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
