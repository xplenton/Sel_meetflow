import { useState, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLanguage } from '../contexts/LanguageContext';
import { usePermissions } from '../lib/permissions';
import Sidebar from '../components/Sidebar';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Progress } from '../components/ui/progress';
import { BarChart3, Users, Video, TrendingUp, Clock, MessageSquare, Award, Shield, PieChart, CalendarClock, ListChecks, CalendarCheck, CheckCircle, Vote, Car, Flag, Disc, Utensils, Send } from 'lucide-react';
import api from '../lib/api';
import DriversLicenseAdminPanel from '../components/admin/DriversLicenseAdminPanel';
import NewsModerationPanel from '../components/NewsModerationPanel';
import CateringHistoryPanel from '../components/admin/CateringHistoryPanel';
import FiletransferAdminOverview from '../components/filetransfer/AdminOverview';

export default function AnalyticsPage() {
  const { t } = useLanguage();
  const { can } = usePermissions();

  // Iter 398 — Granulare Tab-Capabilities. Statt blanket-Admin-Gate wird
  // jeder Tab einzeln per Capability geprueft, sodass Admins z.B.
  // Buchhaltung nur „Catering-Historie", Fuhrpark-Manager nur „Führerscheine"
  // freischalten koennen, ohne ihnen Voll-Admin zu geben.
  const tabAccess = {
    meetings: can('analytics.view_meetings'),
    scheduling: can('analytics.view_scheduling'),
    surveys: can('analytics.view_surveys'),
    bookings: can('analytics.view_bookings'),
    stats: can('analytics.view_platform_stats'),
    filetransfer: can('filetransfer.admin'),
    'catering-history': can('analytics.view_catering_history'),
    'drivers-licenses': can('users.view_drivers_license'),
    'news-moderation': can('news.moderate'),
  };
  const hasAnyAccess = Object.values(tabAccess).some(Boolean);
  // Erster zugänglicher Tab — wird als defaultValue genutzt
  const firstAccessibleTab = Object.entries(tabAccess).find(([, v]) => v)?.[0];

  const [overview, setOverview] = useState(null);
  const [attendance, setAttendance] = useState([]);
  const [modes, setModes] = useState({});
  const [daily, setDaily] = useState([]);
  const [topUsers, setTopUsers] = useState([]);
  const [scheduling, setScheduling] = useState(null);
  const [loading, setLoading] = useState(true);

  // Iter 396 — Plattform-Statistiken (ehem. /admin?tab=stats) jetzt in
  // Auswertungen; nutzt /admin/stats Endpoint. Bewusst eigenständig per
  // useQuery (statt Promise.all mit Analytics-Endpoints), damit ein
  // 401-Refresh nicht die anderen Analytics-Calls blockt.
  const platformStatsQ = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: async () => (await api.get('/admin/stats')).data,
    enabled: tabAccess.stats,
    retry: 1,
    staleTime: 30_000,
  });
  const platformStats = platformStatsQ.data;

  const fetchAll = useCallback(async () => {
    try {
      const [ov, att, md, dy, tu, sc] = await Promise.all([
        api.get('/analytics/overview'),
        api.get('/analytics/attendance'),
        api.get('/analytics/meeting-modes'),
        api.get('/analytics/daily-meetings'),
        api.get('/analytics/top-users'),
        api.get('/analytics/scheduling'),
      ]);
      setOverview(ov.data);
      setAttendance(att.data);
      setModes(md.data);
      setDaily(dy.data);
      setTopUsers(tu.data);
      setScheduling(sc.data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (!hasAnyAccess) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 flex items-center justify-center">
          <div className="text-center" data-testid="analytics-no-access">
            <Shield className="w-12 h-12 text-[#C87967] mx-auto mb-3" />
            <h2 className="text-lg font-medium">Keine Berechtigung</h2>
            <p className="text-sm text-[#6B7280] mt-2">Dir wurde keine Analytics-Capability zugewiesen. Bitte wende dich an einen Administrator.</p>
          </div>
        </main>
      </div>
    );
  }

  const avgAttendance = attendance.length > 0 ? Math.round(attendance.reduce((s, a) => s + a.rate, 0) / attendance.length) : 0;
  const totalModes = Object.values(modes).reduce((s, v) => s + v, 0);
  const maxDaily = Math.max(...daily.map(d => d.count), 1);

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="analytics-page">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-2xl font-medium tracking-tight mb-6 text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('analytics')}</h1>

          {loading ? <div className="text-center py-12 text-[#9CA3AF]">Loading...</div> : (
            <>
              {/* Overview Cards - Row 1: Meetings */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-4">
                {[
                  { label: t('totalUsers'), value: overview?.total_users || 0, icon: Users, color: '#4A5D4E' },
                  { label: t('totalMeetings'), value: overview?.total_meetings || 0, icon: Video, color: '#D4A373' },
                  { label: t('activeMeetings'), value: overview?.active_meetings || 0, icon: TrendingUp, color: '#6B8E23' },
                  { label: t('totalMessages'), value: overview?.total_messages || 0, icon: MessageSquare, color: '#9CA3AF' },
                  { label: t('averageAttendance'), value: `${avgAttendance}%`, icon: BarChart3, color: '#4A5D4E' },
                ].map((s, i) => (
                  <div key={i} className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid={`overview-card-${i}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <s.icon className="w-4 h-4" style={{ color: s.color }} />
                      <span className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280]">{s.label}</span>
                    </div>
                    <span className="text-2xl font-light text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{s.value}</span>
                  </div>
                ))}
              </div>

              {/* Overview Cards - Row 2: Scheduling */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
                {[
                  { label: 'Terminplanungen', value: overview?.total_schedule_polls || 0, icon: CalendarClock, color: '#4A5D4E' },
                  { label: 'Umfragen', value: overview?.total_general_polls || 0, icon: ListChecks, color: '#D4A373' },
                  { label: 'Buchungen', value: overview?.total_bookings || 0, icon: CalendarCheck, color: '#6B8E23' },
                  { label: 'Termin-Abstimmungen', value: overview?.total_schedule_votes || 0, icon: Vote, color: '#C87967' },
                  { label: 'Umfrage-Stimmen', value: overview?.total_general_votes || 0, icon: Vote, color: '#9CA3AF' },
                ].map((s, i) => (
                  <div key={`s${i}`} className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid={`scheduling-card-${i}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <s.icon className="w-4 h-4" style={{ color: s.color }} />
                      <span className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280]">{s.label}</span>
                    </div>
                    <span className="text-2xl font-light text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{s.value}</span>
                  </div>
                ))}
              </div>

              <Tabs defaultValue={firstAccessibleTab} className="mb-6">
                {/* Iter 397/398 — Tabs in 2 logische Gruppen + capability-
                    basiertes Rendering: jeder Tab erscheint nur, wenn der
                    User die zugehoerige Capability hat. */}
                <div className="space-y-2 mb-4">
                  {(tabAccess.meetings || tabAccess.scheduling || tabAccess.surveys || tabAccess.bookings || tabAccess.stats || tabAccess.filetransfer) && (
                    <>
                      <div className="text-[10px] uppercase tracking-[0.15em] font-semibold text-[#6B7280]">Nutzungs-Auswertung</div>
                      <TabsList className="bg-[#F3F4F1] rounded-lg flex flex-wrap h-auto gap-1 p-1">
                        {tabAccess.meetings && <TabsTrigger value="meetings" className="rounded-lg text-sm"><Video className="w-3.5 h-3.5 mr-1" />Meetings</TabsTrigger>}
                        {tabAccess.scheduling && <TabsTrigger value="scheduling" className="rounded-lg text-sm" data-testid="tab-scheduling-analytics"><CalendarClock className="w-3.5 h-3.5 mr-1" />Terminplanung</TabsTrigger>}
                        {tabAccess.surveys && <TabsTrigger value="surveys" className="rounded-lg text-sm" data-testid="tab-surveys-analytics"><ListChecks className="w-3.5 h-3.5 mr-1" />Umfragen</TabsTrigger>}
                        {tabAccess.bookings && <TabsTrigger value="bookings" className="rounded-lg text-sm" data-testid="tab-bookings-analytics"><CalendarCheck className="w-3.5 h-3.5 mr-1" />Buchungen</TabsTrigger>}
                        {tabAccess.stats && <TabsTrigger value="stats" className="rounded-lg text-sm" data-testid="tab-platform-stats"><BarChart3 className="w-3.5 h-3.5 mr-1" />Statistiken</TabsTrigger>}
                        {tabAccess.filetransfer && <TabsTrigger value="filetransfer" className="rounded-lg text-sm" data-testid="tab-filetransfer-analytics"><Send className="w-3.5 h-3.5 mr-1" />Filetransfer</TabsTrigger>}
                      </TabsList>
                    </>
                  )}
                  {(tabAccess['catering-history'] || tabAccess['drivers-licenses'] || tabAccess['news-moderation']) && (
                    <>
                      <div className="text-[10px] uppercase tracking-[0.15em] font-semibold text-[#6B7280] pt-1">Datenpflege</div>
                      <TabsList className="bg-[#F3F4F1] rounded-lg flex flex-wrap h-auto gap-1 p-1">
                        {tabAccess['catering-history'] && <TabsTrigger value="catering-history" className="rounded-lg text-sm" data-testid="tab-catering-history"><Utensils className="w-3.5 h-3.5 mr-1" />Catering-Artikel</TabsTrigger>}
                        {tabAccess['drivers-licenses'] && <TabsTrigger value="drivers-licenses" className="rounded-lg text-sm" data-testid="tab-drivers-licenses-analytics"><Car className="w-3.5 h-3.5 mr-1" />Führerscheine</TabsTrigger>}
                        {tabAccess['news-moderation'] && <TabsTrigger value="news-moderation" className="rounded-lg text-sm" data-testid="tab-news-moderation-analytics"><Flag className="w-3.5 h-3.5 mr-1" />News-Moderation</TabsTrigger>}
                      </TabsList>
                    </>
                  )}
                </div>

                {/* MEETINGS TAB */}
                <TabsContent value="meetings">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                    {/* Daily Chart */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="daily-chart">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-[#4A5D4E]" /> {t('dailyMeetings')} - {t('last14Days')}
                      </h3>
                      <div className="flex items-end gap-1.5 h-32">
                        {daily.map((d, i) => (
                          <div key={i} className="flex-1 flex flex-col items-center gap-1">
                            <div className="w-full bg-[#4A5D4E] rounded-t-sm transition-all hover:bg-[#3E4E42]"
                              style={{ height: `${Math.max((d.count / maxDaily) * 100, 4)}%` }} title={`${d.date}: ${d.count}`} />
                            <span className="text-[8px] text-[#9CA3AF]">{d.date}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Modes */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="modes-chart">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <PieChart className="w-4 h-4 text-[#D4A373]" /> {t('meetingModes')}
                      </h3>
                      <div className="space-y-3">
                        {Object.entries(modes).map(([mode, count]) => {
                          const pct = totalModes > 0 ? Math.round((count / totalModes) * 100) : 0;
                          const colors = { standard: '#4A5D4E', moderated: '#D4A373', webinar: '#6B8E23', training: '#C87967' };
                          return (
                            <div key={mode}>
                              <div className="flex justify-between text-xs mb-1">
                                <span className="capitalize text-[#4B5563]">{t(mode)}</span>
                                <span className="text-[#9CA3AF]">{count} ({pct}%)</span>
                              </div>
                              <div className="h-2 bg-[#F3F4F1] rounded-full overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: colors[mode] || '#9CA3AF' }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Attendance */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="attendance-table">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-[#6B8E23]" /> {t('attendanceRate')}
                      </h3>
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {attendance.map((a, i) => (
                          <div key={a.meeting_id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-[#F3F4F1]">
                            <div className="flex-1 min-w-0">
                              <span className="text-xs font-medium text-[#1C1F1D] truncate block">{a.title}</span>
                              <span className="text-[10px] text-[#9CA3AF]">{a.attended}/{a.invited}</span>
                            </div>
                            <div className="w-16"><Progress value={a.rate} className="h-1.5" /></div>
                            <span className={`text-xs font-medium ${a.rate >= 70 ? 'text-[#6B8E23]' : a.rate >= 40 ? 'text-[#D4A373]' : 'text-[#C87967]'}`}>{a.rate}%</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Top Users */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="top-users-table">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <Award className="w-4 h-4 text-[#D4A373]" /> {t('topUsers')}
                      </h3>
                      <div className="space-y-2">
                        {topUsers.map((u, i) => (
                          <div key={u.user_id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-[#F3F4F1]">
                            <div className="w-6 h-6 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-[10px] font-bold text-[#4A5D4E] flex-shrink-0">{i + 1}</div>
                            <div className="flex-1 min-w-0">
                              <span className="text-xs font-medium text-[#1C1F1D] truncate block">{u.name}</span>
                              <div className="flex gap-2 text-[10px] text-[#9CA3AF]">
                                <span>{u.meetings_hosted} hosted</span><span>{u.meetings_joined} joined</span>
                              </div>
                            </div>
                            <Badge className="text-[9px] bg-[#4A5D4E]/10 text-[#4A5D4E]">{u.activity_score}</Badge>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </TabsContent>

                {/* SCHEDULING TAB */}
                <TabsContent value="scheduling">
                  <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="schedule-polls-analytics">
                    <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                      <CalendarClock className="w-4 h-4 text-[#4A5D4E]" /> Terminplanungen ({scheduling?.schedule_polls?.length || 0})
                    </h3>
                    {!scheduling?.schedule_polls?.length ? (
                      <p className="text-sm text-[#9CA3AF] text-center py-6">{t('noSchedulingsYet')}</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-[#E2E4E0]">
                              <th className="text-left text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Titel</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Status</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Zeitfenster</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Abstimmungen</th>
                              <th className="text-left text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">{t('bestTime')}</th>
                              <th className="text-left text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Ersteller</th>
                            </tr>
                          </thead>
                          <tbody>
                            {scheduling.schedule_polls.map(p => (
                              <tr key={p.poll_id} className="border-b border-[#F3F4F1] hover:bg-[#F9F9F8]">
                                <td className="py-2.5 text-xs font-medium text-[#1C1F1D] max-w-[200px] truncate">{p.title}</td>
                                <td className="py-2.5 text-center">
                                  <Badge className={`text-[9px] ${p.status === 'confirmed' ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#4A5D4E]/10 text-[#4A5D4E]'}`}>
                                    {p.status === 'confirmed' ? 'Bestätigt' : 'Offen'}
                                  </Badge>
                                </td>
                                <td className="py-2.5 text-center text-xs text-[#6B7280]">{p.slots}</td>
                                <td className="py-2.5 text-center text-xs font-medium text-[#1C1F1D]">{p.votes}</td>
                                <td className="py-2.5 text-xs text-[#6B7280]">{p.best_slot || '-'}</td>
                                <td className="py-2.5 text-xs text-[#9CA3AF]">{p.creator}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </TabsContent>

                {/* SURVEYS TAB */}
                <TabsContent value="surveys">
                  <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="general-polls-analytics">
                    <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-[#D4A373]" /> Umfragen ({scheduling?.general_polls?.length || 0})
                    </h3>
                    {!scheduling?.general_polls?.length ? (
                      <p className="text-sm text-[#9CA3AF] text-center py-6">{t('noSurveysAtAll')}</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-[#E2E4E0]">
                              <th className="text-left text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Titel</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Typ</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Optionen</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Stimmen</th>
                              <th className="text-left text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Fuehrend</th>
                              <th className="text-center text-[10px] uppercase tracking-wider font-bold text-[#6B7280] pb-2">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {scheduling.general_polls.map(p => (
                              <tr key={p.poll_id} className="border-b border-[#F3F4F1] hover:bg-[#F9F9F8]">
                                <td className="py-2.5 text-xs font-medium text-[#1C1F1D] max-w-[200px] truncate">{p.title}</td>
                                <td className="py-2.5 text-center">
                                  <Badge className="text-[9px] bg-[#F3F4F1] text-[#6B7280]">
                                    {p.poll_type === 'single' ? 'Einzeln' : p.poll_type === 'multiple' ? 'Mehrfach' : 'Prioritaet'}
                                  </Badge>
                                </td>
                                <td className="py-2.5 text-center text-xs text-[#6B7280]">{p.options}</td>
                                <td className="py-2.5 text-center text-xs font-medium text-[#1C1F1D]">{p.votes}</td>
                                <td className="py-2.5 text-xs text-[#6B8E23] font-medium">{p.winner || '-'}{p.winner_score > 0 ? ` (${p.winner_score})` : ''}</td>
                                <td className="py-2.5 text-center">
                                  <Badge className={`text-[9px] ${p.status === 'closed' ? 'bg-[#C87967]/10 text-[#C87967]' : 'bg-[#4A5D4E]/10 text-[#4A5D4E]'}`}>
                                    {p.status === 'closed' ? 'Geschlossen' : 'Offen'}
                                  </Badge>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </TabsContent>

                {/* BOOKINGS TAB */}
                <TabsContent value="bookings">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Bookings by Day */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="bookings-chart">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <CalendarCheck className="w-4 h-4 text-[#6B8E23]" /> Buchungen nach Tag
                      </h3>
                      {scheduling?.booking_by_day?.length > 0 ? (
                        <div className="space-y-2">
                          {scheduling.booking_by_day.map(d => {
                            const maxB = Math.max(...scheduling.booking_by_day.map(x => x.count), 1);
                            return (
                              <div key={d.date} className="flex items-center gap-3">
                                <span className="text-xs text-[#6B7280] w-24 flex-shrink-0">{d.date}</span>
                                <div className="flex-1 bg-[#F3F4F1] rounded-full h-3 overflow-hidden">
                                  <div className="h-full bg-[#6B8E23] rounded-full" style={{ width: `${(d.count / maxB) * 100}%` }} />
                                </div>
                                <span className="text-xs font-medium text-[#1C1F1D] w-6 text-right">{d.count}</span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-[#9CA3AF] text-center py-6">{t('noBookingsYet')}</p>
                      )}
                    </div>

                    {/* Top Booking Hosts */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="top-hosts">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-2">
                        <Award className="w-4 h-4 text-[#D4A373]" /> Top Hosts (Buchungen)
                      </h3>
                      {scheduling?.top_booking_hosts?.length > 0 ? (
                        <div className="space-y-2">
                          {scheduling.top_booking_hosts.map((h, i) => (
                            <div key={h.name} className="flex items-center gap-3 p-2 rounded-lg hover:bg-[#F3F4F1]">
                              <div className="w-6 h-6 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-[10px] font-bold text-[#4A5D4E]">{i + 1}</div>
                              <span className="text-xs font-medium text-[#1C1F1D] flex-1">{h.name}</span>
                              <Badge className="text-[9px] bg-[#6B8E23]/10 text-[#6B8E23]">{h.count} Buchungen</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-[#9CA3AF] text-center py-6">{t('noBookingsYet')}</p>
                      )}
                    </div>

                    {/* Summary Cards */}
                    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 lg:col-span-2" data-testid="booking-summary">
                      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">Buchungs-Übersicht</h3>
                      <div className="grid grid-cols-3 gap-4">
                        <div className="text-center p-4 bg-[#F3F4F1] rounded-xl">
                          <span className="text-2xl font-light text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{overview?.total_bookings || 0}</span>
                          <p className="text-[10px] text-[#6B7280] mt-1 uppercase tracking-wider font-bold">Gesamt</p>
                        </div>
                        <div className="text-center p-4 bg-[#6B8E23]/5 rounded-xl">
                          <span className="text-2xl font-light text-[#6B8E23]" style={{ fontFamily: 'Manrope' }}>{overview?.confirmed_bookings || 0}</span>
                          <p className="text-[10px] text-[#6B7280] mt-1 uppercase tracking-wider font-bold">Bestätigt</p>
                        </div>
                        <div className="text-center p-4 bg-[#C87967]/5 rounded-xl">
                          <span className="text-2xl font-light text-[#C87967]" style={{ fontFamily: 'Manrope' }}>{overview?.cancelled_bookings || 0}</span>
                          <p className="text-[10px] text-[#6B7280] mt-1 uppercase tracking-wider font-bold">Storniert</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </TabsContent>

                {/* Iter 396 — STATISTIKEN TAB (ehem. Verwaltung → Monitoring → Statistiken) */}
                <TabsContent value="stats" data-testid="tab-content-platform-stats">
                  {!platformStats ? (
                    <div className="text-sm text-[#9CA3AF] text-center py-12">Statistiken werden geladen …</div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="platform-stats-grid">
                      {[
                        { label: t('totalUsers'), value: platformStats.total_users, icon: Users, color: 'text-[#4A5D4E]' },
                        { label: t('totalMeetings'), value: platformStats.total_meetings, icon: Video, color: 'text-[#D4A373]' },
                        { label: t('activeMeetings'), value: platformStats.active_meetings, icon: BarChart3, color: 'text-[#6B8E23]' },
                        { label: t('totalMessages'), value: platformStats.total_messages, icon: MessageSquare, color: 'text-[#9CA3AF]' },
                        { label: t('endedMeetings'), value: platformStats.ended_meetings, icon: Disc, color: 'text-[#C87967]' },
                        { label: t('polls'), value: platformStats.total_polls, icon: BarChart3, color: 'text-[#4A5D4E]' },
                      ].map((s, i) => (
                        <div key={i} className="bg-white border border-[#E2E4E0] rounded-xl p-6 animate-fade-in"
                          style={{ animationDelay: `${i * 0.05}s` }} data-testid={`platform-stat-card-${i}`}>
                          <div className="flex items-center gap-3 mb-3">
                            <div className="w-10 h-10 rounded-lg bg-[#F3F4F1] flex items-center justify-center">
                              <s.icon className={`w-5 h-5 ${s.color}`} />
                            </div>
                            <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">{s.label}</span>
                          </div>
                          <span className="text-3xl font-light text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{s.value}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Iter 397 — CATERING-ARTIKEL TAB (Datenpflege) */}
                <TabsContent value="catering-history" data-testid="tab-content-catering-history">
                  <CateringHistoryPanel />
                </TabsContent>

                {/* Iter 387 — FILETRANSFER NUTZUNGS-AUSWERTUNG (ehem. Filetransfer → Adminübersicht) */}
                <TabsContent value="filetransfer" data-testid="tab-content-filetransfer-analytics">
                  <FiletransferAdminOverview />
                </TabsContent>

                {/* Iter 396 — FÜHRERSCHEINE TAB (ehem. Verwaltung → Monitoring → Führerscheine) */}
                <TabsContent value="drivers-licenses" data-testid="tab-content-drivers-licenses">
                  <DriversLicenseAdminPanel />
                </TabsContent>

                {/* Iter 396 — NEWS-MODERATION TAB (ehem. Verwaltung → Monitoring → News-Moderation) */}
                <TabsContent value="news-moderation" data-testid="tab-content-news-moderation">
                  <NewsModerationPanel />
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
