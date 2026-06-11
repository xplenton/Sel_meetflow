import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from '../components/Sidebar';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import {
  Users, Clock, MessageSquare, FileText, ArrowLeft, Download,
  CheckCircle, XCircle, LogOut, UserCheck
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

export default function AttendanceReportPage() {
  const { meetingId } = useParams();
  const { user } = useAuth();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchReport = useCallback(async () => {
    try {
      const { data } = await api.get(`/meetings/${meetingId}/attendance-report`);
      setReport(data);
    } catch {
      toast.error('Bericht konnte nicht geladen werden');
    } finally { setLoading(false); }
  }, [meetingId]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const handleExportPdf = async () => {
    try {
      const response = await api.get(`/meetings/${meetingId}/attendance-report/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `anwesenheit_${report?.title || 'meeting'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF heruntergeladen');
    } catch {
      toast.error('PDF-Export fehlgeschlagen');
    }
  };

  const statusIcon = (status) => {
    if (status === 'aktiv') return <CheckCircle className="w-3.5 h-3.5 text-[#4A5D4E]" />;
    if (status === 'verlassen') return <LogOut className="w-3.5 h-3.5 text-[#D4A373]" />;
    return <XCircle className="w-3.5 h-3.5 text-[#9CA3AF]" />;
  };

  const statusLabel = (status) => {
    if (status === 'aktiv') return 'Aktiv';
    if (status === 'verlassen') return 'Verlassen';
    return 'Abwesend';
  };

  const roleLabel = (role) => {
    if (role === 'host') return 'Host';
    if (role === 'co-host') return 'Co-Host';
    return 'Teilnehmer';
  };

  const formatTime = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 flex items-center justify-center">
          <div className="animate-spin w-6 h-6 border-2 border-[#4A5D4E] border-t-transparent rounded-full" />
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="attendance-report-page">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link to="/dashboard" className="p-2 rounded-lg hover:bg-[#F3F4F1] text-[#9CA3AF]">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                Anwesenheitsbericht
              </h1>
              <p className="text-sm text-[#9CA3AF]">{report?.title}</p>
            </div>
          </div>
          <Button onClick={handleExportPdf} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs h-8"
            data-testid="export-attendance-pdf">
            <Download className="w-3.5 h-3.5 mr-1.5" />PDF Export
          </Button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { icon: Users, label: 'Teilnehmer', value: report?.total_participants || 0, color: '#4A5D4E' },
            { icon: UserCheck, label: 'Aktiv', value: report?.active_participants || 0, color: '#4A5D4E' },
            { icon: MessageSquare, label: 'Chat-Nachrichten', value: report?.total_chat_messages || 0, color: '#3B82F6' },
            { icon: FileText, label: 'Dokumente', value: report?.total_documents || 0, color: '#D4A373' },
          ].map((stat, i) => (
            <Card key={i} className="border-[#E2E4E0]" data-testid={`stat-${stat.label.toLowerCase().replace(/[^a-z]/g, '-')}`}>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${stat.color}15` }}>
                  <stat.icon className="w-4.5 h-4.5" style={{ color: stat.color }} />
                </div>
                <div>
                  <p className="text-lg font-semibold text-[#1C1F1D]">{stat.value}</p>
                  <p className="text-[10px] text-[#9CA3AF]">{stat.label}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Participants Table */}
        <Card className="border-[#E2E4E0]">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2">
              <Users className="w-4 h-4 text-[#4A5D4E]" />
              Teilnehmer ({report?.participants?.length || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="max-h-[500px]">
              <div className="divide-y divide-[#E2E4E0]">
                {report?.participants?.map((p, i) => (
                  <div key={p.user_id || i}
                    className="flex items-center gap-4 px-5 py-3 hover:bg-[#F9F9F8] transition-colors"
                    data-testid={`participant-row-${i}`}>
                    {/* Avatar */}
                    <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                      <span className="text-xs font-medium text-[#4A5D4E]">
                        {p.name?.[0]?.toUpperCase() || '?'}
                      </span>
                    </div>

                    {/* Name + Role */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#1C1F1D] truncate">{p.name}</span>
                        <Badge variant="outline" className="text-[8px] border-[#E2E4E0] px-1.5">
                          {roleLabel(p.role)}
                        </Badge>
                      </div>
                      <p className="text-[10px] text-[#9CA3AF] truncate">{p.email}</p>
                    </div>

                    {/* Time */}
                    <div className="hidden md:block text-right flex-shrink-0">
                      <p className="text-[10px] text-[#6B7280]">
                        <Clock className="w-2.5 h-2.5 inline mr-0.5" />
                        {formatTime(p.joined_at)} — {p.left_at ? formatTime(p.left_at) : 'jetzt'}
                      </p>
                      <p className="text-[10px] font-medium text-[#4A5D4E]">
                        {p.duration_minutes} Min.
                      </p>
                    </div>

                    {/* Chat count */}
                    <div className="flex-shrink-0 text-center" data-testid={`chat-count-${i}`}>
                      <p className="text-sm font-medium text-[#1C1F1D]">{p.chat_messages}</p>
                      <p className="text-[8px] text-[#9CA3AF]">Chat</p>
                    </div>

                    {/* Signatures */}
                    <div className="flex-shrink-0 text-center" data-testid={`sig-count-${i}`}>
                      <p className="text-sm font-medium text-[#1C1F1D]">{p.signatures}</p>
                      <p className="text-[8px] text-[#9CA3AF]">Sign.</p>
                    </div>

                    {/* Status */}
                    <div className="flex items-center gap-1 flex-shrink-0" data-testid={`status-${i}`}>
                      {statusIcon(p.status)}
                      <span className={`text-[10px] font-medium ${
                        p.status === 'aktiv' ? 'text-[#4A5D4E]' :
                        p.status === 'verlassen' ? 'text-[#D4A373]' : 'text-[#9CA3AF]'
                      }`}>{statusLabel(p.status)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
