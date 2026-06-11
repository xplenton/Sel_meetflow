/**
 * PresetTooltip — Hover-/Long-Press-Tooltip mit Auflistung aller
 * Capabilities eines Capability-Presets (iter 375).
 *
 * Verwendung:
 *   <PresetTooltip preset={preset} capsMeta={capsMeta}>
 *     <button>News-Redakteur (+4)</button>
 *   </PresetTooltip>
 *
 * `capsMeta` ist ein Objekt von cap_key → {label, category}, geliefert
 * durch `GET /api/admin/capabilities`. Wenn nicht übergeben, faellt die
 * Anzeige auf die Roh-Cap-Keys zurück (immer noch besser als leerer
 * Title-Tooltip).
 */
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';

const CATEGORY_LABELS = {
  module: 'Modul-Sichtbarkeit',
  news: 'News',
  meetings: 'Meetings',
  chat: 'Chat',
  documents: 'Dokumente & Whiteboard',
  scheduling: 'Terminplanung',
  surveys: 'Umfragen',
  tasks: 'Aufgaben',
  resources: 'Ressourcen & Catering',
  invoices: 'Rechnungen',
  fleet: 'Fuhrpark',
  admin: 'Admin',
  global: 'Global',
};

export default function PresetTooltip({ preset, capsMeta, children, side = 'top' }) {
  if (!preset) return children;
  const caps = preset.capabilities || [];

  // Gruppieren nach Kategorie für bessere Lesbarkeit.
  const byCategory = caps.reduce((acc, key) => {
    const meta = capsMeta?.[key];
    const cat = meta?.category || 'other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push({ key, label: meta?.label || key });
    return acc;
  }, {});

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent
          side={side}
          sideOffset={6}
          className="bg-white text-[#1A1D1B] border border-[#E2E4E0] shadow-lg max-w-[360px] p-0 z-[200]"
          data-testid={`preset-tooltip-${preset.preset_id}`}
        >
          <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0]">
            <div className="text-xs font-bold text-[#1A1D1B]">{preset.label}</div>
            {preset.description && (
              <div className="text-[10px] text-[#6B7280] mt-0.5 leading-snug">{preset.description}</div>
            )}
            <div className="text-[10px] text-[#4A5D4E] mt-1 font-medium">
              {caps.length} Recht{caps.length === 1 ? '' : 'e'} vorausgewaehlt
            </div>
          </div>
          <div className="px-3 py-2 max-h-[280px] overflow-y-auto space-y-2">
            {Object.entries(byCategory).map(([cat, list]) => (
              <div key={cat}>
                <div className="text-[9px] uppercase tracking-wider text-[#4A5D4E] font-bold mb-1">
                  {CATEGORY_LABELS[cat] || cat}
                </div>
                <ul className="space-y-0.5">
                  {list.map(({ key, label }) => (
                    <li key={key} className="text-[10px] text-[#1A1D1B] leading-snug flex gap-1.5">
                      <span className="text-[#4A5D4E] flex-shrink-0">+</span>
                      <span className="flex-1">{label}</span>
                      <code className="text-[9px] text-[#9CA3AF] font-mono">{key}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
