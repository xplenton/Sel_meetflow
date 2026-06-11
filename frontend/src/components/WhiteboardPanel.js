import { useState, useRef, useEffect, useCallback } from 'react';
import { Button } from '../components/ui/button';
import {
  X, Pen, Eraser, Trash2, Undo2, Maximize2, Minimize2, Minus, Plus, Download,
  Square, Circle, MoveRight, StickyNote, GripVertical
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { useLanguage } from '../contexts/LanguageContext';

const COLORS = [
  '#1C1F1D', '#E25C5C', '#4A5D4E', '#3B82F6',
  '#F59E0B', '#8B5CF6', '#EC4899', '#F97316',
];
const NOTE_COLORS = ['#FEF3C7', '#DBEAFE', '#D1FAE5', '#FCE7F3', '#E9D5FF'];

export default function WhiteboardPanel({ meetingId, wsRef, userId, onClose }) {
  const { t } = useLanguage();
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [tool, setTool] = useState('pen');
  const [color, setColor] = useState('#1C1F1D');
  const [brushSize, setBrushSize] = useState(3);
  const [fullscreen, setFullscreen] = useState(false);
  const [notes, setNotes] = useState([]);
  const [editingNote, setEditingNote] = useState(null);
  const isDrawing = useRef(false);
  const lastPoint = useRef(null);
  const shapeStart = useRef(null);
  const currentStroke = useRef(null);
  const strokesRef = useRef([]);
  const strokeIdCounter = useRef(0);
  const noteColorIdx = useRef(0);
  const draggingNote = useRef(null);
  const dragOffset = useRef({ x: 0, y: 0 });

  const getCtx = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    return canvas.getContext('2d');
  }, []);

  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const rect = container.getBoundingClientRect();
    const dpr = 2;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    redrawAll();
  }, []); // eslint-disable-line

  const drawStroke = (ctx, stroke) => {
    const t = stroke.tool;
    ctx.globalCompositeOperation = t === 'eraser' ? 'destination-out' : 'source-over';
    ctx.strokeStyle = t === 'eraser' ? '#F9F9F8' : stroke.color;
    ctx.lineWidth = t === 'eraser' ? stroke.width * 4 : stroke.width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.fillStyle = 'transparent';

    if (t === 'rect' && stroke.points.length >= 2) {
      const p0 = stroke.points[0], p1 = stroke.points[stroke.points.length - 1];
      ctx.beginPath();
      ctx.rect(p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
      ctx.stroke();
    } else if (t === 'circle' && stroke.points.length >= 2) {
      const p0 = stroke.points[0], p1 = stroke.points[stroke.points.length - 1];
      const rx = Math.abs(p1.x - p0.x) / 2, ry = Math.abs(p1.y - p0.y) / 2;
      const cx = (p0.x + p1.x) / 2, cy = (p0.y + p1.y) / 2;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (t === 'arrow' && stroke.points.length >= 2) {
      const p0 = stroke.points[0], p1 = stroke.points[stroke.points.length - 1];
      const angle = Math.atan2(p1.y - p0.y, p1.x - p0.x);
      const headLen = Math.max(12, stroke.width * 4);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p1.x - headLen * Math.cos(angle - Math.PI / 6), p1.y - headLen * Math.sin(angle - Math.PI / 6));
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p1.x - headLen * Math.cos(angle + Math.PI / 6), p1.y - headLen * Math.sin(angle + Math.PI / 6));
      ctx.stroke();
    } else if (stroke.points && stroke.points.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (let i = 1; i < stroke.points.length; i++) {
        ctx.lineTo(stroke.points[i].x, stroke.points[i].y);
      }
      ctx.stroke();
    }
    ctx.globalCompositeOperation = 'source-over';
  };

  const redrawAll = useCallback(() => {
    const ctx = getCtx();
    const canvas = canvasRef.current;
    if (!ctx || !canvas) return;
    const dpr = 2;
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    for (const stroke of strokesRef.current) {
      drawStroke(ctx, stroke);
    }
  }, [getCtx]);

  // Load existing strokes + notes
  useEffect(() => {
    (async () => {
      try {
        const [strokesRes, notesRes] = await Promise.all([
          api.get(`/meetings/${meetingId}/whiteboard`),
          api.get(`/meetings/${meetingId}/whiteboard/notes`),
        ]);
        strokesRef.current = strokesRes.data.map(s => ({
          id: s.stroke_id, points: s.points, color: s.color,
          width: s.width, tool: s.tool, userId: s.user_id,
        }));
        setNotes(notesRes.data.map(n => ({
          id: n.note_id, x: n.x, y: n.y, text: n.text,
          color: n.color, userId: n.user_id,
        })));
        redrawAll();
      } catch {}
    })();
  }, [meetingId, redrawAll]);

  useEffect(() => {
    resizeCanvas();
    const handleResize = () => resizeCanvas();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [resizeCanvas, fullscreen]);

  // WS listener
  useEffect(() => {
    const ws = wsRef?.current;
    if (!ws) return;
    const handler = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      if (data.type === 'whiteboard-draw' && data.sender !== userId) {
        const stroke = data.stroke;
        if (!stroke) return;
        let existing = strokesRef.current.find(s => s.id === stroke.id);
        if (existing) { existing.points = stroke.points; }
        else { strokesRef.current.push({ ...stroke, userId: data.sender }); }
        redrawAll();
      } else if (data.type === 'whiteboard-clear' && data.sender !== userId) {
        strokesRef.current = [];
        setNotes([]);
        redrawAll();
      } else if (data.type === 'whiteboard-undo' && data.sender !== userId) {
        for (let i = strokesRef.current.length - 1; i >= 0; i--) {
          if (strokesRef.current[i].userId === data.sender) { strokesRef.current.splice(i, 1); break; }
        }
        redrawAll();
      } else if (data.type === 'whiteboard-note' && data.sender !== userId) {
        const note = data.note;
        if (note) {
          setNotes(prev => {
            const idx = prev.findIndex(n => n.id === note.id);
            if (idx >= 0) { const u = [...prev]; u[idx] = { ...u[idx], ...note }; return u; }
            return [...prev, note];
          });
        }
      } else if (data.type === 'whiteboard-note-delete' && data.sender !== userId) {
        setNotes(prev => prev.filter(n => n.id !== data.note_id));
      }
    };
    ws.addEventListener('message', handler);
    return () => ws.removeEventListener('message', handler);
  }, [wsRef, userId, redrawAll]);

  const getCanvasPos = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const isShapeTool = ['rect', 'circle', 'arrow'].includes(tool);

  const startDraw = (e) => {
    if (tool === 'note') return;
    e.preventDefault();
    isDrawing.current = true;
    const pos = getCanvasPos(e);
    lastPoint.current = pos;
    shapeStart.current = pos;
    strokeIdCounter.current += 1;
    const strokeId = `s_${userId}_${Date.now()}_${strokeIdCounter.current}`;
    currentStroke.current = { id: strokeId, points: [pos], color, width: brushSize, tool, userId };
  };

  const draw = (e) => {
    if (tool === 'note') return;
    e.preventDefault();
    if (!isDrawing.current || !currentStroke.current) return;
    const pos = getCanvasPos(e);

    if (isShapeTool) {
      currentStroke.current.points = [shapeStart.current, pos];
      redrawAll();
      const ctx = getCtx();
      if (ctx) drawStroke(ctx, currentStroke.current);
    } else {
      currentStroke.current.points.push(pos);
      const ctx = getCtx();
      if (ctx && lastPoint.current) {
        ctx.beginPath();
        ctx.strokeStyle = tool === 'eraser' ? '#F9F9F8' : color;
        ctx.lineWidth = tool === 'eraser' ? brushSize * 4 : brushSize;
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';
        ctx.moveTo(lastPoint.current.x, lastPoint.current.y);
        ctx.lineTo(pos.x, pos.y);
        ctx.stroke();
        ctx.globalCompositeOperation = 'source-over';
      }
      lastPoint.current = pos;
      if (currentStroke.current.points.length % 3 === 0) {
        wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-draw', stroke: currentStroke.current }));
      }
    }
  };

  const endDraw = () => {
    if (tool === 'note' || !isDrawing.current || !currentStroke.current) return;
    isDrawing.current = false;
    if (currentStroke.current.points.length >= 2) {
      strokesRef.current.push({ ...currentStroke.current });
      wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-draw', stroke: currentStroke.current }));
      wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-stroke-complete', stroke: currentStroke.current }));
      redrawAll();
    }
    currentStroke.current = null;
    lastPoint.current = null;
    shapeStart.current = null;
  };

  const handleCanvasClick = (e) => {
    if (tool !== 'note') return;
    const pos = getCanvasPos(e);
    const noteId = `n_${userId}_${Date.now()}`;
    const noteColor = NOTE_COLORS[noteColorIdx.current % NOTE_COLORS.length];
    noteColorIdx.current += 1;
    const note = { id: noteId, x: pos.x, y: pos.y, text: '', color: noteColor, userId };
    setNotes(prev => [...prev, note]);
    setEditingNote(noteId);
    wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-note', note }));
    wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-note-complete', note }));
  };

  const updateNote = (noteId, updates) => {
    setNotes(prev => prev.map(n => n.id === noteId ? { ...n, ...updates } : n));
    const note = notes.find(n => n.id === noteId);
    if (note) {
      const updated = { ...note, ...updates };
      wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-note', note: updated }));
      wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-note-complete', note: updated }));
    }
  };

  const deleteNote = (noteId) => {
    setNotes(prev => prev.filter(n => n.id !== noteId));
    wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-note-delete', note_id: noteId }));
  };

  const handleUndo = () => {
    for (let i = strokesRef.current.length - 1; i >= 0; i--) {
      if (strokesRef.current[i].userId === userId) { strokesRef.current.splice(i, 1); break; }
    }
    redrawAll();
    wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-undo' }));
  };

  const handleClear = () => {
    strokesRef.current = [];
    setNotes([]);
    redrawAll();
    wsRef?.current?.send(JSON.stringify({ type: 'whiteboard-clear' }));
  };

  const adjustBrush = (delta) => setBrushSize(prev => Math.max(1, Math.min(20, prev + delta)));

  const handleExportPng = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const tmp = document.createElement('canvas');
    tmp.width = canvas.width; tmp.height = canvas.height;
    const tmpCtx = tmp.getContext('2d');
    tmpCtx.fillStyle = '#FFFFFF';
    tmpCtx.fillRect(0, 0, tmp.width, tmp.height);
    tmpCtx.drawImage(canvas, 0, 0);
    const url = tmp.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = url; a.download = `whiteboard_${meetingId}_${Date.now()}.png`; a.click();
  };

  const startNoteDrag = (e, noteId) => {
    e.stopPropagation();
    const note = notes.find(n => n.id === noteId);
    if (!note) return;
    draggingNote.current = noteId;
    const rect = e.currentTarget.parentElement.getBoundingClientRect();
    dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const onMove = (me) => {
      const container = containerRef.current;
      if (!container || !draggingNote.current) return;
      const cr = container.getBoundingClientRect();
      const nx = me.clientX - cr.left - dragOffset.current.x;
      const ny = me.clientY - cr.top - dragOffset.current.y;
      updateNote(draggingNote.current, { x: Math.max(0, nx), y: Math.max(0, ny) });
    };
    const onUp = () => {
      draggingNote.current = null;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const ToolBtn = ({ value, icon: Icon, label, testId }) => (
    <Button variant={tool === value ? 'default' : 'ghost'} size="sm"
      onClick={() => setTool(value)}
      className={`h-7 w-7 p-0 ${tool === value ? 'bg-[#4A5D4E] text-white' : ''}`}
      data-testid={testId} title={label}>
      <Icon className="w-3.5 h-3.5" />
    </Button>
  );

  return (
    <div className={`bg-[#F9F9F8] flex flex-col ${fullscreen ? 'fixed inset-0 z-50' : 'flex-1 border-l border-[#E2E4E0]'}`}
      data-testid="whiteboard-panel">
      {/* Toolbar */}
      <div className="h-11 flex items-center justify-between px-3 border-b border-[#E2E4E0] flex-shrink-0 bg-white">
        <div className="flex items-center gap-1">
          <ToolBtn value="pen" icon={Pen} label={t('penTool')} testId="wb-tool-pen" />
          <ToolBtn value="eraser" icon={Eraser} label={t('eraserTool')} testId="wb-tool-eraser" />
          <div className="w-px h-5 bg-[#E2E4E0] mx-0.5" />
          <ToolBtn value="rect" icon={Square} label={t('rectTool')} testId="wb-tool-rect" />
          <ToolBtn value="circle" icon={Circle} label={t('circleTool')} testId="wb-tool-circle" />
          <ToolBtn value="arrow" icon={MoveRight} label={t('arrowTool')} testId="wb-tool-arrow" />
          <ToolBtn value="note" icon={StickyNote} label={t('stickyNoteTool')} testId="wb-tool-note" />
          <div className="w-px h-5 bg-[#E2E4E0] mx-0.5" />
          <div className="flex gap-0.5" data-testid="wb-color-palette">
            {COLORS.map(c => (
              <button key={c} onClick={() => { setColor(c); if (tool === 'eraser') setTool('pen'); }}
                className={`w-4 h-4 rounded-full border-2 transition-transform ${
                  color === c && tool !== 'eraser' ? 'border-[#1C1F1D] scale-125' : 'border-transparent'}`}
                style={{ backgroundColor: c }} data-testid={`wb-color-${c.replace('#', '')}`} />
            ))}
          </div>
          <div className="w-px h-5 bg-[#E2E4E0] mx-0.5" />
          <div className="flex items-center gap-0.5">
            <Button variant="ghost" size="sm" onClick={() => adjustBrush(-1)} className="h-6 w-6 p-0" data-testid="wb-brush-minus"><Minus className="w-3 h-3" /></Button>
            <span className="text-[10px] text-[#6B7280] w-4 text-center" data-testid="wb-brush-size">{brushSize}</span>
            <Button variant="ghost" size="sm" onClick={() => adjustBrush(1)} className="h-6 w-6 p-0" data-testid="wb-brush-plus"><Plus className="w-3 h-3" /></Button>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={handleUndo} className="h-7 px-2 text-[10px] text-[#6B7280]" data-testid="wb-undo"><Undo2 className="w-3.5 h-3.5 mr-1" />Undo</Button>
          <Button variant="ghost" size="sm" onClick={handleClear} className="h-7 px-2 text-[10px] text-[#C87967]" data-testid="wb-clear"><Trash2 className="w-3.5 h-3.5 mr-1" />Clear</Button>
          <Button variant="ghost" size="sm" onClick={handleExportPng} className="h-7 px-2 text-[10px] text-[#4A5D4E]" data-testid="wb-export-png"><Download className="w-3.5 h-3.5 mr-1" />PNG</Button>
          <Button variant="ghost" size="sm" onClick={() => setFullscreen(!fullscreen)} className="h-7 w-7 p-0 text-[#6B7280]" data-testid="wb-fullscreen">
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose} className="h-7 w-7 p-0 text-[#9CA3AF]" data-testid="wb-close"><X className="w-3.5 h-3.5" /></Button>
        </div>
      </div>

      {/* Canvas + Notes */}
      <div ref={containerRef} className={`flex-1 overflow-hidden relative ${tool === 'note' ? 'cursor-cell' : 'cursor-crosshair'}`}
        data-testid="wb-canvas-container">
        <canvas ref={canvasRef} className="touch-none"
          onMouseDown={startDraw} onMouseMove={draw} onMouseUp={endDraw} onMouseLeave={endDraw}
          onTouchStart={startDraw} onTouchMove={draw} onTouchEnd={endDraw}
          onClick={handleCanvasClick} data-testid="wb-canvas" />

        {/* Sticky Notes Overlay */}
        {notes.map(note => (
          <div key={note.id}
            className="absolute w-36 min-h-[80px] rounded-lg shadow-md border border-black/5 p-1.5 flex flex-col"
            style={{ left: note.x, top: note.y, backgroundColor: note.color, zIndex: 10 }}
            data-testid={`wb-note-${note.id}`}>
            <div className="flex items-center justify-between mb-1">
              <button onMouseDown={(e) => startNoteDrag(e, note.id)}
                className="cursor-grab p-0.5 text-black/30 hover:text-black/50" data-testid={`wb-note-drag-${note.id}`}>
                <GripVertical className="w-3 h-3" />
              </button>
              <button onClick={() => deleteNote(note.id)}
                className="p-0.5 text-black/30 hover:text-[#C87967]" data-testid={`wb-note-delete-${note.id}`}>
                <X className="w-3 h-3" />
              </button>
            </div>
            {editingNote === note.id ? (
              <textarea
                autoFocus
                value={note.text}
                onChange={(e) => setNotes(prev => prev.map(n => n.id === note.id ? { ...n, text: e.target.value } : n))}
                onBlur={() => { updateNote(note.id, { text: note.text }); setEditingNote(null); }}
                onKeyDown={(e) => { if (e.key === 'Escape') { updateNote(note.id, { text: note.text }); setEditingNote(null); }}}
                className="flex-1 bg-transparent border-none outline-none text-[11px] text-[#1C1F1D] resize-none min-h-[50px] placeholder:text-black/30"
                placeholder={t('notePlaceholder')}
                data-testid={`wb-note-textarea-${note.id}`}
              />
            ) : (
              <div className="flex-1 text-[11px] text-[#1C1F1D] cursor-text min-h-[50px]"
                onDoubleClick={() => setEditingNote(note.id)} data-testid={`wb-note-text-${note.id}`}>
                {note.text || <span className="text-black/30 italic">{t('doubleClickToEdit')}</span>}
              </div>
            )}
          </div>
        ))}

        {/* Note tool hint */}
        {tool === 'note' && notes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-sm text-[#9CA3AF]">{t('clickToPlaceNote')}</span>
          </div>
        )}
      </div>
    </div>
  );
}
