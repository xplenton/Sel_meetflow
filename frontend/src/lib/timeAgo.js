// Relative time formatter: "vor 3 Min", "vor 2 Std", "gestern", "vor 3 Tagen"
export function timeAgo(iso, locale = 'de') {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  const sec = Math.floor(diffMs / 1000);
  const min = Math.floor(sec / 60);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);

  const isDE = locale === 'de';
  if (sec < 30) return isDE ? 'gerade eben' : 'just now';
  if (min < 1) return isDE ? `vor ${sec} Sek` : `${sec}s ago`;
  if (min < 60) return isDE ? `vor ${min} Min` : `${min}m ago`;
  if (hr < 24) return isDE ? `vor ${hr} Std` : `${hr}h ago`;
  if (day === 1) return isDE ? 'gestern' : 'yesterday';
  if (day < 7) return isDE ? `vor ${day} Tagen` : `${day}d ago`;
  return d.toLocaleDateString(isDE ? 'de-DE' : 'en-US', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
