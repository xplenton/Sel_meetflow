import { Badge } from '../../ui/badge';
import { Users, MapPin } from 'lucide-react';

export default function BookingResourceHeader({ resource }) {
  return (
    <div className="rounded-lg bg-[#F3F4F1] border border-[#E2E4E0] p-3 space-y-1" data-testid="booking-resource-info">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="font-medium text-[#1C1F1D]">{resource.name}</div>
        <div className="flex gap-1">
          {resource.is_splitable && (
            <Badge variant="outline" className="text-[10px] border-[#4A5D4E] text-[#4A5D4E]">Teilbar</Badge>
          )}
          {resource.requires_approval && (
            <Badge variant="outline" className="text-[10px] border-amber-500 text-amber-700">Freigabepflicht</Badge>
          )}
        </div>
      </div>
      <div className="text-xs text-[#6B7280] flex items-center gap-3 flex-wrap">
        {(resource.location || resource.building || resource.floor) && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="w-3 h-3" />
            {[resource.location, resource.building, resource.floor].filter(Boolean).join(' · ')}
          </span>
        )}
        {resource.capacity && (
          <span className="inline-flex items-center gap-1">
            <Users className="w-3 h-3" /> {resource.capacity} Personen
          </span>
        )}
        {resource.seats && <span>{resource.seats} Sitzplätze · {resource.license_plate}</span>}
        {resource.desk_number && <span>Desk-Nr. {resource.desk_number}</span>}
      </div>
      {resource.equipment?.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {resource.equipment.slice(0, 6).map((e, idx) => (
            <Badge key={`eq-${idx}`} variant="outline" className="text-[10px]">{e}</Badge>
          ))}
        </div>
      )}
    </div>
  );
}
