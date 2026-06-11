import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Pen, Type, RotateCcw, Check } from 'lucide-react';

export default function SignaturePad({ onSign, onCancel, signerName, showPosition }) {
  const [mode, setMode] = useState('draw');
  const [typedSig, setTypedSig] = useState(signerName || '');
  const [posPage, setPosPage] = useState(1);
  const [posX, setPosX] = useState(0);
  const [posY, setPosY] = useState(0);
  const canvasRef = useRef(null);
  const isDrawing = useRef(false);
  const lastPoint = useRef(null);

  const initCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * 2;
    canvas.height = rect.height * 2;
    ctx.scale(2, 2);
    ctx.strokeStyle = '#1C1F1D';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }, []);

  useEffect(() => { initCanvas(); }, [initCanvas]);

  const getPos = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const startDraw = (e) => {
    e.preventDefault();
    isDrawing.current = true;
    lastPoint.current = getPos(e);
  };

  const draw = (e) => {
    e.preventDefault();
    if (!isDrawing.current) return;
    const ctx = canvasRef.current.getContext('2d');
    const pos = getPos(e);
    ctx.beginPath();
    ctx.moveTo(lastPoint.current.x, lastPoint.current.y);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    lastPoint.current = pos;
  };

  const endDraw = () => { isDrawing.current = false; lastPoint.current = null; };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  const handleSubmit = () => {
    const posData = showPosition ? { pos_x: posX, pos_y: posY, page: posPage } : {};
    if (mode === 'draw') {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const dataUrl = canvas.toDataURL('image/png');
      onSign({ type: 'drawn', signature_data: dataUrl, ...posData });
    } else {
      if (!typedSig.trim()) return;
      onSign({ type: 'typed', signature_data: typedSig.trim(), ...posData });
    }
  };

  return (
    <div className="space-y-4" data-testid="signature-pad">
      <Tabs value={mode} onValueChange={setMode}>
        <TabsList className="grid w-full grid-cols-2 h-9">
          <TabsTrigger value="draw" className="text-xs" data-testid="sig-tab-draw">
            <Pen className="w-3.5 h-3.5 mr-1.5" />Zeichnen
          </TabsTrigger>
          <TabsTrigger value="type" className="text-xs" data-testid="sig-tab-type">
            <Type className="w-3.5 h-3.5 mr-1.5" />Tippen
          </TabsTrigger>
        </TabsList>

        <TabsContent value="draw" className="mt-3">
          <div className="relative border border-[#E2E4E0] rounded-lg bg-white overflow-hidden">
            <canvas
              ref={canvasRef}
              className="w-full h-32 cursor-crosshair touch-none"
              onMouseDown={startDraw}
              onMouseMove={draw}
              onMouseUp={endDraw}
              onMouseLeave={endDraw}
              onTouchStart={startDraw}
              onTouchMove={draw}
              onTouchEnd={endDraw}
              data-testid="signature-canvas"
            />
            <div className="absolute bottom-1 left-2 text-[10px] text-[#9CA3AF] pointer-events-none">
              Hier unterschreiben
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={clearCanvas}
            className="mt-1.5 text-xs text-[#9CA3AF] h-7" data-testid="clear-signature-btn">
            <RotateCcw className="w-3 h-3 mr-1" />Leeren
          </Button>
        </TabsContent>

        <TabsContent value="type" className="mt-3">
          <Input
            value={typedSig}
            onChange={(e) => setTypedSig(e.target.value)}
            placeholder="Ihr Name als Unterschrift"
            className="text-lg italic font-serif"
            data-testid="signature-typed-input"
          />
          <div className="mt-3 p-4 border border-[#E2E4E0] rounded-lg bg-white min-h-[80px] flex items-center justify-center">
            <span className="text-2xl italic font-serif text-[#1C1F1D]" data-testid="signature-preview">
              {typedSig || 'Vorschau'}
            </span>
          </div>
        </TabsContent>
      </Tabs>

      {showPosition && (
        <div className="flex gap-2 items-center" data-testid="signature-position">
          <div className="flex-1">
            <label className="text-[10px] text-[#6B7280] block mb-0.5">Seite</label>
            <Input type="number" min={1} value={posPage} onChange={(e) => setPosPage(parseInt(e.target.value) || 1)}
              className="h-7 text-xs" data-testid="sig-pos-page" />
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-[#6B7280] block mb-0.5">X-Position</label>
            <Input type="number" min={0} value={posX} onChange={(e) => setPosX(parseInt(e.target.value) || 0)}
              className="h-7 text-xs" data-testid="sig-pos-x" />
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-[#6B7280] block mb-0.5">Y-Position</label>
            <Input type="number" min={0} value={posY} onChange={(e) => setPosY(parseInt(e.target.value) || 0)}
              className="h-7 text-xs" data-testid="sig-pos-y" />
          </div>
        </div>
      )}

      <div className="flex gap-2 justify-end">
        <Button variant="outline" size="sm" onClick={onCancel} className="text-xs h-8" data-testid="cancel-signature-btn">
          Abbrechen
        </Button>
        <Button size="sm" onClick={handleSubmit}
          className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs h-8" data-testid="submit-signature-btn">
          <Check className="w-3.5 h-3.5 mr-1" />Unterschreiben
        </Button>
      </div>
    </div>
  );
}
