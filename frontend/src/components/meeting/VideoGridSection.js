import VirtualBgCanvas from '../VirtualBgCanvas';
import { RemoteVideo, VideoMirror } from './VideoTiles';

/**
 * VideoGridSection — renders the local + remote video tiles in a responsive
 * grid, plus the virtual-background canvas/badge and the "camera off" avatar
 * fallback. Extracted from LiveMeetingPage during the iter 215 refactor.
 *
 * State & refs (camera/virtualBg/localStream) stay in the parent — this
 * component is purely presentational.
 */
export default function VideoGridSection({
  user,
  cameraOn,
  micOn: _micOn,
  handRaised,
  virtualBg,
  virtualBgUrl,
  localVideoRef,
  localStreamRef,
  bgCanvasRef,
  onBgCanvasReady,
  onBgPainting,
  remoteEntries,
  remoteNames,
  participants,
  presentedDoc,
  whiteboardOpen,
  gridCols,
}) {
  const containerClass =
    `${presentedDoc || whiteboardOpen ? 'hidden sm:block w-64 flex-shrink-0' : 'flex-1'} p-2 sm:p-4 overflow-auto`;
  const innerGridClass = `grid ${presentedDoc ? 'grid-cols-1' : gridCols} gap-2 sm:gap-3 h-full`;

  return (
    <div className={containerClass}>
      <div className={innerGridClass}>
        {/* Local video tile */}
        <div className="video-tile rounded-xl relative overflow-hidden" data-testid="local-video-tile">
          {/* Hidden persistent video for WebRTC stream */}
          <video ref={localVideoRef} autoPlay muted playsInline className="hidden" />

          {cameraOn ? (
            virtualBg !== 'none' ? (
              <VirtualBgCanvas
                stream={localStreamRef.current}
                bgType={virtualBg}
                bgUrl={virtualBgUrl}
                className="w-full h-full object-cover"
                mirrored={false}
                onCanvasReady={(c) => {
                  if (bgCanvasRef) bgCanvasRef.current = c;
                  onBgCanvasReady?.(c);
                }}
                onPainting={onBgPainting}
              />
            ) : (
              <VideoMirror stream={localStreamRef.current}
                className="w-full h-full object-cover" />
            )
          ) : (
            <div className="w-full h-full flex items-center justify-center"
              style={{ backgroundColor: '#2A2D2B' }}>
              <div className="w-20 h-20 rounded-full bg-[#4A5D4E] flex items-center justify-center text-white text-2xl font-medium shadow-lg">
                {user?.name?.[0]?.toUpperCase() || 'U'}
              </div>
            </div>
          )}

          {/* Virtual BG Badge */}
          {virtualBg !== 'none' && (
            <div className="absolute top-2 left-2 z-20 bg-black/60 text-white text-[9px] px-2 py-0.5 rounded-full flex items-center gap-1"
              data-testid="virtual-bg-badge">
              <span className="w-1.5 h-1.5 rounded-full bg-[#6B8E23]" />
              {virtualBg === 'blur' ? 'Blur' :
               virtualBg === 'official' ? 'Klinik' :
               virtualBg.charAt(0).toUpperCase() + virtualBg.slice(1)}
            </div>
          )}

          <div className="participant-name z-20">{user?.name} (You)</div>
          {handRaised && <div className="absolute top-2 right-2 text-xl z-20">✋</div>}
        </div>

        {/* Remote videos */}
        {remoteEntries.map(([peerId, stream]) => (
          <RemoteVideo key={peerId} peerId={peerId} stream={stream}
            participants={participants} displayName={remoteNames[peerId]} />
        ))}
      </div>
    </div>
  );
}
