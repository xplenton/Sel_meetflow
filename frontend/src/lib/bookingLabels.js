/**
 * Iter 325 — Klartext-Hilfsfunktionen für Ressourcen-Buchungen.
 *
 * Verwendet in:
 *  - `pages/ResourcesPage.js` (Tab „Meine Buchungen", Tabelle)
 *  - `pages/DashboardPage.js` (Widget „Meine nächsten Buchungen")
 *
 * Backend liefert seit Iter 325 zusätzlich:
 *   resource_name, resource_type, resource_license_plate, resource_building,
 *   resource_floor, resource_desk_number, resource_parking_location,
 *   user_name, user_email, booked_for_name, booked_for_email
 */

/**
 * Detaillierter Ressourcen-Klartext.
 *  - Fahrzeug:    "Audi A4 · M-AB 1234"
 *  - Raum:        "Boardroom · Gebäude B · 3. Etage"
 *  - Arbeitsplatz: "Desk 17 · Gebäude B · 2. Etage"
 *  - Fallback:    nur Name oder ID
 */
export function describeResource(b) {
  if (!b) return '';
  const name = b.resource_name || '';
  const type = b.resource_type;
  const parts = [];
  if (type === 'vehicle') {
    if (name) parts.push(name);
    if (b.resource_license_plate) parts.push(b.resource_license_plate);
    if (b.resource_parking_location) parts.push(`Stellplatz ${b.resource_parking_location}`);
  } else if (type === 'desk') {
    const lbl = b.resource_desk_number ? `${name || 'Desk'} ${b.resource_desk_number}` : name;
    if (lbl) parts.push(lbl);
    if (b.resource_building) parts.push(`Gebäude ${b.resource_building}`);
    if (b.resource_floor) parts.push(formatFloor(b.resource_floor));
  } else if (type === 'room') {
    // Iter 339 — Sub-Raum: zeige Parent + Bereich-Kennung, nicht nur den
    // bloßen Sub-Namen. So sieht der User "Großer Saal — Bereich A" statt
    // nur "A" oder fälschlich des Parents allein.
    if (b.resource_parent_id && (b.resource_parent_name || b.resource_sub_id)) {
      const parentLabel = b.resource_parent_name || '';
      const subLabel = b.resource_sub_id || name;
      const combined = parentLabel ? `${parentLabel} — Bereich ${subLabel}` : `Bereich ${subLabel}`;
      parts.push(combined);
    } else if (name) {
      parts.push(name);
    }
    if (b.resource_building) parts.push(`Gebäude ${b.resource_building}`);
    if (b.resource_floor) parts.push(formatFloor(b.resource_floor));
  } else {
    if (name) parts.push(name);
    if (b.resource_location) parts.push(b.resource_location);
  }
  return parts.join(' · ');
}

/**
 * User-Klartext: "Gebucht von Max Mustermann" bzw. — falls Stellvertreter-
 * Buchung — "Gebucht für Max Mustermann von Jane Doe".
 * Gibt leeren String zurück, wenn keine User-Daten gehydratet wurden.
 */
export function describeBookingUser(b) {
  if (!b) return '';
  const booker = b.user_name || b.user_email;
  const beneficiary = b.booked_for_name || b.booked_for_email;
  if (b.booked_for_user_id && beneficiary && beneficiary !== booker) {
    return `Gebucht für ${beneficiary}${booker ? ` von ${booker}` : ''}`;
  }
  if (booker) return `Gebucht von ${booker}`;
  return '';
}

function formatFloor(f) {
  // Backend liefert das floor-Feld als String — Zahlen werden zu „N. Etage"
  // veredelt, alles andere (z. B. „EG", „UG1") wird unverändert übernommen.
  if (f === null || f === undefined || f === '') return '';
  const num = Number(f);
  if (!Number.isNaN(num) && Number.isFinite(num)) {
    if (num === 0) return 'EG';
    return `${num}. Etage`;
  }
  return String(f);
}
