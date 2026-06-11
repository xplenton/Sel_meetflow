/**
 * SlackWebhookWizard (iter 245).
 * Inline-Anleitung im Profil — 5 nummerierte Schritte mit CSS-Mockups,
 * Code-Snippet, Direktlink zur Slack-Doku.
 *
 * Extracted from /app/frontend/src/pages/ProfilePage.js (iter 247).
 */

function MockBrowserCard({ url, content, cta }) {
  return (
    <div className="rounded border border-[#E2E4E0] bg-white text-[9px] overflow-hidden">
      <div className="bg-[#F3F4F1] border-b border-[#E2E4E0] px-1.5 py-0.5 flex items-center gap-1">
        <span className="w-1.5 h-1.5 bg-[#EF4444] rounded-full"></span>
        <span className="w-1.5 h-1.5 bg-[#FBBF24] rounded-full"></span>
        <span className="w-1.5 h-1.5 bg-[#10B981] rounded-full"></span>
        {url && <span className="ml-1 text-[#9CA3AF] truncate">{url}</span>}
      </div>
      <div className="p-2 text-center">
        <div className="text-[#1C1F1D] mb-1">{content}</div>
        {cta && (
          <span className="inline-block px-2 py-0.5 rounded bg-[#4A154B] text-white text-[8px] font-medium">
            {cta}
          </span>
        )}
      </div>
    </div>
  );
}

function MockToggleCard({ label, on }) {
  return (
    <div className="rounded border border-[#E2E4E0] bg-white p-2 flex items-center justify-between gap-2">
      <span className="text-[10px] text-[#1C1F1D] truncate">{label}</span>
      <span className={`w-7 h-3.5 rounded-full flex items-center ${on ? 'bg-[#10B981] justify-end' : 'bg-[#D1D5DB] justify-start'}`}>
        <span className="w-3 h-3 bg-white rounded-full m-0.5 shadow-sm"></span>
      </span>
    </div>
  );
}

function MockCodeCard({ text }) {
  return (
    <div className="rounded bg-[#1C1F1D] text-[#A7C4A0] font-mono text-[8.5px] px-2 py-1.5 leading-relaxed break-all">
      {text}
    </div>
  );
}

function MockSuccessCard({ text }) {
  return (
    <div className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-[10px] text-emerald-700 font-medium">
      {text}
    </div>
  );
}

export default function SlackWebhookWizard({ language }) {
  const isDe = language === 'de';
  const steps = isDe ? [
    {
      title: 'Slack-App erstellen',
      body: 'Öffne api.slack.com/apps und klicke "Create New App" → "From scratch". Wähle einen Namen (z.B. "MeetFlow Office") und den Workspace, in dem die Notification ankommen soll.',
      mock: <MockBrowserCard url="api.slack.com/apps" content="Your Apps" cta="Create New App" />,
    },
    {
      title: 'Incoming Webhooks aktivieren',
      body: 'Im linken Menü zu "Incoming Webhooks". Schalte den Toggle "Activate Incoming Webhooks" auf ON.',
      mock: <MockToggleCard label="Activate Incoming Webhooks" on />,
    },
    {
      title: 'Webhook-Channel hinzufügen',
      body: 'Klicke unten auf "Add New Webhook to Workspace". Slack fragt dich, in welchen Channel die Nachrichten gepostet werden sollen (z.B. #team-office).',
      mock: <MockBrowserCard url="" content="In welchen Kanal posten?" cta="#team-office  →  Allow" />,
    },
    {
      title: 'Webhook-URL kopieren',
      body: 'Slack zeigt jetzt deine Webhook-URL — sie beginnt mit "https://hooks.slack.com/services/...". Kopiere die komplette URL.',
      mock: <MockCodeCard text="https://hooks.slack.com/services/T0…/B0…/Abc123" />,
    },
    {
      title: 'URL hier einfügen + Testen',
      body: 'Füge die URL oben in das Eingabefeld "Slack-Webhook URL" ein, klicke "Speichern" und danach "Testen". Bei Erfolg erscheint eine Test-Message in deinem Slack-Channel.',
      mock: <MockSuccessCard text='✓ "Test from MeetFlow — Verbindung erfolgreich"' />,
    },
  ] : [
    { title: 'Create Slack App', body: 'Open api.slack.com/apps and click "Create New App" → "From scratch". Pick a name (e.g. "MeetFlow Office") and your workspace.', mock: <MockBrowserCard url="api.slack.com/apps" content="Your Apps" cta="Create New App" /> },
    { title: 'Activate Incoming Webhooks', body: 'In the left menu navigate to "Incoming Webhooks". Toggle "Activate Incoming Webhooks" to ON.', mock: <MockToggleCard label="Activate Incoming Webhooks" on /> },
    { title: 'Add channel webhook', body: 'Click "Add New Webhook to Workspace" at the bottom. Slack asks which channel to post into (e.g. #team-office).', mock: <MockBrowserCard url="" content="Post to which channel?" cta="#team-office  →  Allow" /> },
    { title: 'Copy the webhook URL', body: 'Slack shows your webhook URL starting with "https://hooks.slack.com/services/…". Copy the full URL.', mock: <MockCodeCard text="https://hooks.slack.com/services/T0…/B0…/Abc123" /> },
    { title: 'Paste & Test', body: 'Paste it into the "Slack webhook URL" field above, click "Save" then "Test". A test message will appear in your Slack channel.', mock: <MockSuccessCard text='✓ "Test from MeetFlow — connection ok"' /> },
  ];

  return (
    <div className="mt-3 rounded-lg border border-[#E2E4E0] bg-[#FAFAF8] p-3 space-y-3"
      data-testid="slack-webhook-wizard">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-[#1C1F1D]">
          {isDe ? 'Slack-Webhook in 5 Schritten einrichten' : 'Slack webhook setup in 5 steps'}
        </div>
        <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noopener noreferrer"
          className="text-[10px] text-[#4A5D4E] hover:underline"
          data-testid="slack-wizard-docs-link">
          {isDe ? 'Offizielle Slack-Doku ↗' : 'Official Slack docs ↗'}
        </a>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {steps.map((s, i) => (
          <div key={i} className="bg-white border border-[#E2E4E0] rounded-lg p-2.5"
            data-testid={`slack-wizard-step-${i + 1}`}>
            <div className="flex items-start gap-2 mb-2">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-[#4A5D4E] text-white text-[10px] font-bold flex items-center justify-center">
                {i + 1}
              </span>
              <div className="text-[11px] font-semibold text-[#1C1F1D] leading-tight">{s.title}</div>
            </div>
            <p className="text-[10px] text-[#6B7280] mb-2 leading-snug">{s.body}</p>
            {s.mock}
          </div>
        ))}
      </div>
      <div className="text-[10px] text-[#9CA3AF] pt-1 border-t border-[#E2E4E0]">
        {isDe
          ? 'Hinweis: Die Webhook-URL ist wie ein Passwort — teile sie niemals öffentlich. MeetFlow speichert sie verschlüsselt und zeigt sie nie wieder im Klartext an.'
          : 'Note: The webhook URL is like a password — never share it publicly. MeetFlow stores it encrypted and never shows it again.'}
      </div>
    </div>
  );
}
