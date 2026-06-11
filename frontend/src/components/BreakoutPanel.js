import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ScrollArea } from '../components/ui/scroll-area';
import { Badge } from '../components/ui/badge';
import {
  X, Plus, Trash2, Play, Square, Shuffle, Megaphone, Users, Clock, ChevronDown, ChevronUp, DoorOpen, LogOut
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
export default function BreakoutPanel({ meetingId, participants, onClose, breakoutContext, onVisitBreakout }) {
  const { t } = useLanguage();
  const [rooms, setRooms] = useState([]);
  const [newRoomName, setNewRoomName] = useState('');
  const [autoCount, setAutoCount] = useState(2);
  const [duration, setDuration] = useState(10);
  const [broadcastMsg, setBroadcastMsg] = useState('');
  const [isActive, setIsActive] = useState(false);
  const [timer, setTimer] = useState(0);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const timerRef = useRef(null);

  const fetchRooms = useCallback(async () => {
    try {
      const { data } = await api.get(`/meetings/${meetingId}/breakout-rooms`);
      setRooms(data);
      const hasOpen = data.some(r => r.status === 'open');
      setIsActive(hasOpen);
    } catch {}
  }, [meetingId]);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  // Timer countdown
  useEffect(() => {
    if (isActive && timer > 0) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          if (prev <= 1) {
            clearInterval(timerRef.current);
            handleEnd();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timerRef.current);
    }
  }, [isActive]); // eslint-disable-line

  const formatTimer = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const activeParticipants = participants.filter(p => p.joined_at && !p.left_at && p.role !== 'host');

  const getParticipantName = (userId) => {
    const p = participants.find(pt => pt.user_id === userId);
    return p?.name || userId;
  };

  const handleCreateRoom = async () => {
    if (!newRoomName.trim()) return;
    try {
      await api.post(`/meetings/${meetingId}/breakout-rooms`, {
        name: newRoomName.trim(), participant_ids: [],
      });
      setNewRoomName('');
      fetchRooms();
    } catch {
      toast.error('Fehler beim Erstellen');
    }
  };

  const handleAutoAssign = async () => {
    setLoading(true);
    try {
      await api.post(`/meetings/${meetingId}/breakout-rooms/auto-assign`, {
        room_count: autoCount,
      });
      toast.success(`${autoCount} Räume erstellt und zugewiesen`);
      fetchRooms();
    } catch {
      toast.error('Fehler bei Auto-Zuweisung');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRoom = async (roomId) => {
    try {
      await api.delete(`/meetings/${meetingId}/breakout-rooms/${roomId}`);
      fetchRooms();
    } catch {}
  };

  const handleAssignParticipant = async (roomId, userId) => {
    const room = rooms.find(r => r.room_id === roomId);
    if (!room) return;
    const ids = [...(room.participant_ids || [])];
    if (ids.includes(userId)) {
      ids.splice(ids.indexOf(userId), 1);
    } else {
      // Remove from other rooms first
      for (const r of rooms) {
        if (r.room_id !== roomId && r.participant_ids?.includes(userId)) {
          await api.put(`/meetings/${meetingId}/breakout-rooms/${r.room_id}`, {
            participant_ids: r.participant_ids.filter(id => id !== userId),
          });
        }
      }
      ids.push(userId);
    }
    await api.put(`/meetings/${meetingId}/breakout-rooms/${roomId}`, {
      participant_ids: ids,
    });
    fetchRooms();
  };

  const handleStart = async () => {
    if (rooms.filter(r => r.status === 'open').length === 0) {
      toast.error('Keine offenen Räume vorhanden');
      return;
    }
    setLoading(true);
    try {
      await api.post(`/meetings/${meetingId}/breakout-rooms/start`, {
        duration: duration * 60,
      });
      setIsActive(true);
      setTimer(duration * 60);
      toast.success('Breakout Rooms gestartet');
      fetchRooms();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Starten');
    } finally {
      setLoading(false);
    }
  };

  const handleEnd = async () => {
    setLoading(true);
    try {
      await api.post(`/meetings/${meetingId}/breakout-rooms/end`);
      setIsActive(false);
      setTimer(0);
      clearInterval(timerRef.current);
      toast.success('Breakout Rooms beendet');
      fetchRooms();
    } catch {
      toast.error('Fehler beim Beenden');
    } finally {
      setLoading(false);
    }
  };

  const handleBroadcast = async () => {
    if (!broadcastMsg.trim()) return;
    try {
      await api.post(`/meetings/${meetingId}/breakout-rooms/broadcast`, {
        message: broadcastMsg,
      });
      setBroadcastMsg('');
      toast.success('Nachricht an alle Räume gesendet');
    } catch {
      toast.error('Fehler beim Senden');
    }
  };

  const toggleExpand = (roomId) => {
    setExpanded(prev => ({ ...prev, [roomId]: !prev[roomId] }));
  };

  const assignedUserIds = new Set(rooms.flatMap(r => r.participant_ids || []));
  const unassigned = activeParticipants.filter(p => !assignedUserIds.has(p.user_id));

  return (
    <div className="space-y-4" data-testid="breakout-panel">
      {/* Active Session Banner */}
      {isActive && (
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-[#4A5D4E]/10 border border-[#4A5D4E]/20"
          data-testid="breakout-active-banner">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[#4A5D4E] animate-pulse" />
            <span className="text-xs font-medium text-[#4A5D4E]">{t('breakoutActive')}</span>
            {timer > 0 && (
              <Badge className="bg-[#4A5D4E] text-white text-[10px]" data-testid="breakout-timer">
                <Clock className="w-3 h-3 mr-1" />{formatTimer(timer)}
              </Badge>
            )}
          </div>
          <Button size="sm" variant="outline" onClick={handleEnd} disabled={loading}
            className="h-6 px-2 text-[10px] border-[#C87967] text-[#C87967]" data-testid="end-breakout-btn">
            <Square className="w-3 h-3 mr-1" />Beenden
          </Button>
        </div>
      )}

      {/* Create / Auto-assign (only when not active) */}
      {!isActive && (
        <>
          <div className="space-y-2">
            <h4 className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider">{t('createRoom')}</h4>
            <div className="flex gap-1">
              <Input value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)}
                placeholder="Raumname..." className="text-xs h-7 flex-1" data-testid="breakout-room-name-input" />
              <Button size="sm" onClick={handleCreateRoom} disabled={!newRoomName.trim()}
                className="h-7 px-2 bg-[#4A5D4E] text-white text-[10px]" data-testid="create-breakout-room-btn">
                <Plus className="w-3 h-3" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <h4 className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider">Auto-Zuweisung</h4>
            <div className="flex gap-1 items-center">
              <Input type="number" min={2} max={10} value={autoCount}
                onChange={(e) => setAutoCount(parseInt(e.target.value) || 2)}
                className="text-xs h-7 w-16" data-testid="auto-assign-count" />
              <span className="text-[10px] text-[#6B7280]">Räume</span>
              <Button size="sm" onClick={handleAutoAssign} disabled={loading || activeParticipants.length === 0}
                className="h-7 px-2 bg-[#4A5D4E] text-white text-[10px] ml-auto" data-testid="auto-assign-btn">
                <Shuffle className="w-3 h-3 mr-1" />Zuweisen
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Rooms List */}
      <div className="space-y-1.5">
        <h4 className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider">
          Räume ({rooms.length})
        </h4>
        {rooms.length === 0 ? (
          <p className="text-[10px] text-[#9CA3AF] py-2">{t('noRoomsCreated')}</p>
        ) : (
          rooms.map(room => {
            const pIds = room.participant_ids || [];
            const isExpanded = expanded[room.room_id];
            return (
              <div key={room.room_id}
                className={`rounded-lg border transition-colors ${
                  room.status === 'open' ? 'border-[#4A5D4E]/20 bg-[#F9F9F8]' : 'border-[#E2E4E0] bg-[#F3F4F1] opacity-60'
                }`}
                data-testid={`breakout-room-${room.room_id}`}>
                <div className="flex items-center gap-2 p-2 cursor-pointer" onClick={() => toggleExpand(room.room_id)}>
                  <div className="w-6 h-6 rounded bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                    <Users className="w-3 h-3 text-[#4A5D4E]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#1C1F1D] truncate">{room.name}</p>
                    <p className="text-[9px] text-[#9CA3AF]">{pIds.length} Teilnehmer</p>
                  </div>
                  {room.status === 'open' && (
                    <Badge variant="outline" className="text-[8px] border-[#4A5D4E]/30 text-[#4A5D4E]">offen</Badge>
                  )}
                  {/* iter 208 — Host kann jeden offenen Raum besuchen, auch
                      wenn er nicht zugewiesen ist. "Verlassen" wenn schon drin. */}
                  {isActive && room.status === 'open' && onVisitBreakout && (
                    breakoutContext?.room_id === room.room_id ? (
                      <button onClick={(e) => { e.stopPropagation(); onVisitBreakout(null); }}
                        className="px-1.5 py-0.5 rounded bg-[#C87967]/10 text-[8px] font-medium text-[#C87967] hover:bg-[#C87967]/20"
                        data-testid={`leave-room-${room.room_id}`}>
                        <LogOut className="w-3 h-3 inline mr-0.5" />Hauptraum
                      </button>
                    ) : (
                      <button onClick={(e) => { e.stopPropagation(); onVisitBreakout(room); }}
                        className="px-1.5 py-0.5 rounded bg-[#4A5D4E]/10 text-[8px] font-medium text-[#4A5D4E] hover:bg-[#4A5D4E]/20"
                        data-testid={`visit-room-${room.room_id}`}>
                        <DoorOpen className="w-3 h-3 inline mr-0.5" />Besuchen
                      </button>
                    )
                  )}
                  {!isActive && (
                    <button onClick={(e) => { e.stopPropagation(); handleDeleteRoom(room.room_id); }}
                      className="p-0.5 rounded text-[#9CA3AF] hover:text-[#C87967]"
                      data-testid={`delete-room-${room.room_id}`}>
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                  {isExpanded ? <ChevronUp className="w-3 h-3 text-[#9CA3AF]" /> : <ChevronDown className="w-3 h-3 text-[#9CA3AF]" />}
                </div>

                {isExpanded && (
                  <div className="px-2 pb-2 space-y-1">
                    {pIds.length === 0 ? (
                      <p className="text-[9px] text-[#9CA3AF] pl-8">{t('noParticipants')}</p>
                    ) : (
                      pIds.map(uid => (
                        <div key={uid} className="flex items-center gap-1.5 pl-8">
                          <div className="w-4 h-4 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center">
                            <span className="text-[7px] font-medium text-[#4A5D4E]">
                              {getParticipantName(uid)?.[0]?.toUpperCase()}
                            </span>
                          </div>
                          <span className="text-[10px] text-[#4B5563] flex-1 truncate">{getParticipantName(uid)}</span>
                          {!isActive && (
                            <button onClick={() => handleAssignParticipant(room.room_id, uid)}
                              className="text-[8px] text-[#C87967] hover:underline">entfernen</button>
                          )}
                        </div>
                      ))
                    )}
                    {/* Add unassigned participants */}
                    {!isActive && unassigned.length > 0 && (
                      <div className="pt-1 pl-8">
                        <p className="text-[8px] text-[#9CA3AF] mb-0.5">Hinzufügen:</p>
                        <div className="flex flex-wrap gap-0.5">
                          {unassigned.map(p => (
                            <button key={p.user_id} onClick={() => handleAssignParticipant(room.room_id, p.user_id)}
                              className="text-[8px] px-1.5 py-0.5 rounded bg-[#4A5D4E]/10 text-[#4A5D4E] hover:bg-[#4A5D4E]/20">
                              + {p.name}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Unassigned participants */}
      {!isActive && unassigned.length > 0 && rooms.length > 0 && (
        <div className="text-[10px] text-[#D4A373]" data-testid="unassigned-warning">
          {unassigned.length} Teilnehmer noch nicht zugewiesen
        </div>
      )}

      {/* Start / Broadcast controls */}
      {rooms.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-[#E2E4E0]">
          {!isActive ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-[#6B7280]" />
                <span className="text-[10px] text-[#6B7280]">Dauer:</span>
                <Input type="number" min={1} max={60} value={duration}
                  onChange={(e) => setDuration(parseInt(e.target.value) || 10)}
                  className="text-xs h-7 w-14" data-testid="breakout-duration-input" />
                <span className="text-[10px] text-[#6B7280]">Min.</span>
              </div>
              <Button onClick={handleStart} disabled={loading}
                className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs h-8"
                data-testid="start-breakout-btn">
                <Play className="w-3.5 h-3.5 mr-1.5" />Breakout Rooms starten
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex gap-1">
                <Input value={broadcastMsg} onChange={(e) => setBroadcastMsg(e.target.value)}
                  placeholder={t('messageToAllRooms')} className="text-xs h-7 flex-1"
                  data-testid="breakout-broadcast-input" />
                <Button size="sm" onClick={handleBroadcast} disabled={!broadcastMsg.trim()}
                  className="h-7 px-2 bg-[#4A5D4E] text-white text-[10px]" data-testid="breakout-broadcast-btn">
                  <Megaphone className="w-3 h-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
