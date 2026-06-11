import '@/App.css';
import { createPortal } from 'react-dom';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { BrandingProvider } from './contexts/BrandingContext';
import { StatusProvider } from './contexts/StatusContext';
import { ChatUnreadProvider } from './contexts/ChatUnreadContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { PermissionsProvider } from './lib/permissions';
import { queryClient } from './lib/queryClient';
import { Toaster } from './components/ui/sonner';
import AuthCallback from './components/AuthCallback';
import KeyboardShortcuts from './components/KeyboardShortcuts';
import OnboardingTour from './components/OnboardingTour';
import InstallPrompt from './components/InstallPrompt';
import OfflineBanner from './components/OfflineBanner';
import SessionExpiryBanner from './components/SessionExpiryBanner';
import IncomingCallModal from './components/IncomingCallModal';
import GuestWelcomeDialog from './components/GuestWelcomeDialog';
import EmailVerificationBanner from './components/EmailVerificationBanner';
import MobileBottomNav from './components/MobileBottomNav';
import PdfViewerHost from './components/resources/PdfViewerHost';
import LicenseBanner from './components/LicenseBanner';
import RoleDowngradeBanner from './components/RoleDowngradeBanner';
import MustChangePasswordBanner from './components/MustChangePasswordBanner';
import { initOfflineQueue } from './lib/offlineQueue';
import { lazy, Suspense, useEffect } from 'react';

// Eager-loaded (auth pages needed immediately)
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import { ForgotPasswordPage, ResetPasswordPage } from './pages/PasswordPages';

// Lazy-loaded pages for code splitting
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const MeetingsPage = lazy(() => import('./pages/MeetingsPage'));
const NewsPage = lazy(() => import('./pages/NewsPage'));
const SurveysPage = lazy(() => import('./pages/SurveysPage'));
const MeetingCreatePage = lazy(() => import('./pages/MeetingCreatePage'));
const PreJoinPage = lazy(() => import('./pages/PreJoinPage'));
const LiveMeetingPage = lazy(() => import('./pages/LiveMeetingPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const MyPermissionsPage = lazy(() => import('./pages/MyPermissionsPage'));
const DiagPage = lazy(() => import('./pages/DiagPage'));
const DiagSharedPage = lazy(() => import('./pages/DiagSharedPage'));
const CalendarPage = lazy(() => import('./pages/CalendarPage'));
const RecordingsPage = lazy(() => import('./pages/RecordingsPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const MeetingSummaryPage = lazy(() => import('./pages/MeetingSummaryPage'));
const SchedulePage = lazy(() => import('./pages/SchedulePage'));
const ScheduleCreatePage = lazy(() => import('./pages/ScheduleCreatePage'));
const ScheduleDetailPage = lazy(() => import('./pages/ScheduleDetailPage'));
const PublicPollPage = lazy(() => import('./pages/PublicPollPage'));
const BookingSettingsPage = lazy(() => import('./pages/BookingSettingsPage'));
const TasksPage = lazy(() => import('./pages/TasksPage'));
const ResourcesPage = lazy(() => import('./pages/ResourcesPage'));
const PublicBookingPage = lazy(() => import('./pages/PublicBookingPage'));
const GeneralPollCreatePage = lazy(() => import('./pages/GeneralPollCreatePage'));
const PublicSurveyPage = lazy(() => import('./pages/PublicSurveyPage'));
const PublicSignPage = lazy(() => import('./pages/PublicSignPage'));
const AttendanceReportPage = lazy(() => import('./pages/AttendanceReportPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const UnsubscribePage = lazy(() => import('./pages/UnsubscribePage'));
const DigitalSignagePage = lazy(() => import('./pages/DigitalSignagePage'));
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage'));
const FiletransferPage = lazy(() => import('./pages/FiletransferPage'));
const PublicTransferPage = lazy(() => import('./pages/PublicTransferPage'));
import QuickShareOverlay from './components/filetransfer/QuickShareOverlay';

function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
      <div className="animate-spin w-6 h-6 border-2 border-[#4A5D4E] border-t-transparent rounded-full" />
    </div>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
        <div className="w-8 h-8 border-2 border-[#4A5D4E] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user === false || user === null) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // iter 312 — render the global mobile bottom-nav next to the page content
  // so phones get a touch-friendly bottom bar without each page having to
  // import it. Desktop keeps the existing Sidebar (the nav is `md:hidden`).
  return (
    <>
      {children}
      <MobileBottomNav />
    </>
  );
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
        <div className="w-8 h-8 border-2 border-[#4A5D4E] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (user && user !== false) return <Navigate to="/dashboard" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();

  // CRITICAL: Detect session_id during render, NOT in useEffect
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Suspense fallback={<PageLoader />}>
    <QuickShareOverlay />
    <Routes>
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      <Route path="/meetings" element={<ProtectedRoute><MeetingsPage /></ProtectedRoute>} />
      <Route path="/news" element={<ProtectedRoute><NewsPage /></ProtectedRoute>} />
      <Route path="/tasks" element={<ProtectedRoute><TasksPage /></ProtectedRoute>} />
      <Route path="/tasks/:taskId" element={<ProtectedRoute><TasksPage /></ProtectedRoute>} />
      <Route path="/resources" element={<ProtectedRoute><ResourcesPage /></ProtectedRoute>} />
      <Route path="/filetransfer" element={<ProtectedRoute><FiletransferPage /></ProtectedRoute>} />
      <Route path="/filetransfer/:transferId" element={<ProtectedRoute><FiletransferPage /></ProtectedRoute>} />
      <Route path="/filetransfer/public/:token" element={<PublicTransferPage />} />
      <Route path="/surveys" element={<ProtectedRoute><SurveysPage /></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
      <Route path="/meetings/create" element={<ProtectedRoute><MeetingCreatePage /></ProtectedRoute>} />
      <Route path="/meetings/:meetingId/join" element={<ProtectedRoute><PreJoinPage /></ProtectedRoute>} />
      <Route path="/meetings/:meetingId/live" element={<ProtectedRoute><LiveMeetingPage /></ProtectedRoute>} />
      {/* Legacy LiveKit-only URL — now identical to /live (iter 140) */}
      <Route path="/meetings/:meetingId/livekit" element={<ProtectedRoute><LiveMeetingPage /></ProtectedRoute>} />
      <Route path="/meetings/:meetingId/summary" element={<ProtectedRoute><MeetingSummaryPage /></ProtectedRoute>} />
      <Route path="/meetings/:meetingId/attendance" element={<ProtectedRoute><AttendanceReportPage /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
      <Route path="/me/permissions" element={<ProtectedRoute><MyPermissionsPage /></ProtectedRoute>} />
      <Route path="/diag" element={<ProtectedRoute><DiagPage /></ProtectedRoute>} />
      <Route path="/diag/shared/:token" element={<DiagSharedPage />} />
      <Route path="/calendar" element={<ProtectedRoute><CalendarPage /></ProtectedRoute>} />
      <Route path="/recordings" element={<ProtectedRoute><RecordingsPage /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
      <Route path="/analytics" element={<ProtectedRoute><AnalyticsPage /></ProtectedRoute>} />
      <Route path="/schedule" element={<ProtectedRoute><SchedulePage /></ProtectedRoute>} />
      {/* German aliases for discoverability — users typing /terminplanung or
          /termine in the URL should land on the schedule pages (iter 149). */}
      <Route path="/terminplanung" element={<Navigate to="/schedule" replace />} />
      <Route path="/termine" element={<Navigate to="/schedule" replace />} />
      <Route path="/umfragen" element={<Navigate to="/schedule?tab=surveys" replace />} />
      <Route path="/schedule/create" element={<ProtectedRoute><ScheduleCreatePage /></ProtectedRoute>} />
      <Route path="/schedule/:pollId" element={<ProtectedRoute><ScheduleDetailPage /></ProtectedRoute>} />
      <Route path="/booking/settings" element={<ProtectedRoute><BookingSettingsPage /></ProtectedRoute>} />
      <Route path="/poll/:shareToken" element={<PublicPollPage />} />
      <Route path="/book/:username" element={<PublicBookingPage />} />
      <Route path="/book/:username/:slug" element={<PublicBookingPage />} />
      <Route path="/schedule/survey/create" element={<ProtectedRoute><GeneralPollCreatePage /></ProtectedRoute>} />
      <Route path="/survey/:shareToken" element={<PublicSurveyPage />} />
      <Route path="/sign/:signToken" element={<PublicSignPage />} />
      <Route path="/unsubscribe/:token" element={<UnsubscribePage />} />
      <Route path="/signage" element={<DigitalSignagePage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
    </Suspense>
  );
}

function App() {
  const toastRoot = document.getElementById('toast-root');
  useEffect(() => { initOfflineQueue(); }, []);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <LanguageProvider>
          <AuthProvider>
            <BrandingProvider>
              <StatusProvider>
                <PermissionsProvider>
                  <ChatUnreadProvider>
                    <KeyboardShortcuts />
                    <OnboardingTour />
                    <InstallPrompt />
                    <OfflineBanner />
                    <SessionExpiryBanner />
                    <EmailVerificationBanner />
                    <IncomingCallModal />
                    <GuestWelcomeDialog />
                    <PdfViewerHost />
                    <LicenseBanner />
                    <RoleDowngradeBanner />
                    <MustChangePasswordBanner />
                    <AppRouter />
                  </ChatUnreadProvider>
                </PermissionsProvider>
              </StatusProvider>
            </BrandingProvider>
          </AuthProvider>
        </LanguageProvider>
        </ThemeProvider>
        {toastRoot && createPortal(<Toaster position="bottom-left" richColors closeButton />, toastRoot)}
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
