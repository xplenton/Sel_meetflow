import { Input } from '../../ui/input';
import { Textarea } from '../../ui/textarea';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { ChevronDown, ChevronUp } from 'lucide-react';

export default function BookingAdvancedDetails({
  resource, showAdvanced, onToggle,
  costCenter, onCostCenter, account, onAccount, costCenters, accounts,
  destination, onDestination, mileageBefore, onMileageBefore,
  purpose, onPurpose,
}) {
  return (
    <>
      <button type="button" onClick={onToggle}
              data-testid="booking-advanced-toggle"
              className="text-xs font-medium text-[#4A5D4E] flex items-center gap-1 hover:underline">
        {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        Weitere Details {showAdvanced ? 'ausblenden' : 'anzeigen'}
      </button>

      {showAdvanced && (
        <div className="space-y-3 border-l-2 border-[#E2E4E0] pl-3" data-testid="booking-advanced-panel">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Kostenstelle</Label>
              <Select value={costCenter || '__none__'} onValueChange={v => onCostCenter(v === '__none__' ? '' : v)}>
                <SelectTrigger data-testid="booking-cost-center"><SelectValue placeholder="— optional —" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— Keine —</SelectItem>
                  {costCenters.map(cc => (
                    <SelectItem key={cc.cost_center_id} value={cc.code}>{cc.code} · {cc.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Konto</Label>
              <Select value={account || '__none__'} onValueChange={v => onAccount(v === '__none__' ? '' : v)}>
                <SelectTrigger data-testid="booking-account"><SelectValue placeholder="— optional —" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— Keines —</SelectItem>
                  {accounts.map(a => (
                    <SelectItem key={a.account_id} value={a.code}>{a.code} · {a.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {resource.type === 'vehicle' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Ziel</Label>
                <Input data-testid="booking-destination" value={destination}
                       onChange={e => onDestination(e.target.value)}
                       placeholder="z.B. Klinikum Mitte" />
              </div>
              <div>
                <Label className="text-xs">Km-Stand (Start)</Label>
                <Input data-testid="booking-mileage-before" type="number" value={mileageBefore}
                       onChange={e => onMileageBefore(e.target.value)} />
              </div>
            </div>
          )}

          <div>
            <Label className="text-xs">Zweck / Notiz</Label>
            <Textarea data-testid="booking-purpose" value={purpose}
                      onChange={e => onPurpose(e.target.value)}
                      rows={2} placeholder="optional" />
          </div>
        </div>
      )}
    </>
  );
}
