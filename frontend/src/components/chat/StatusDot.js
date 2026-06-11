// Presence dot: online | away | dnd | offline.
const MAP = {
  online:  '#6B8E23',
  away:    '#D4A373',
  busy:    '#D4A373', // legacy alias
  dnd:     '#C87967',
  offline: 'transparent',
};

const TITLES = {
  online: 'Online',
  away: 'Abwesend',
  dnd: 'Nicht stoeren',
  offline: 'Offline',
};

export default function StatusDot({ status, size = 'sm', absolute = true, border = true }) {
  const key = status || 'offline';
  const color = MAP[key] || 'transparent';
  const sizeClass = size === 'lg' ? 'w-3 h-3' : size === 'md' ? 'w-2.5 h-2.5' : 'w-2 h-2';
  if (key === 'offline') {
    // Hollow dot with border for offline
    return (
      <div
        className={`${absolute ? 'absolute bottom-0 right-0' : 'inline-block'} ${sizeClass} rounded-full bg-white ${border ? 'border-2 border-[#C9CBC7]' : ''}`}
        title={TITLES[key]}
      />
    );
  }
  return (
    <div
      className={`${absolute ? 'absolute bottom-0 right-0' : 'inline-block'} ${sizeClass} rounded-full ${border ? 'border-2 border-white' : ''}`}
      style={{ backgroundColor: color }}
      title={TITLES[key]}
    />
  );
}
