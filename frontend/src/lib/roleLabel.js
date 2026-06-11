/**
 * Iter 379 — Zentrales Mapping: System-Rollen-ID -> deutscher Anzeigename.
 *
 * Backend nutzt nach wie vor die englischen IDs (`admin`, `moderator`,
 * `member`, `guest`) — sie werden NUR für die UI übersetzt.
 *
 * Verwendung:
 *   import { roleLabel } from '../lib/roleLabel';
 *   <Badge>{roleLabel(user.role)}</Badge>
 */

const ROLE_DE = {
  admin: 'Admin',
  moderator: 'Moderator',
  member: 'Mitarbeiter',
  guest: 'Gast',
  // Legacy-IDs (vor Iter 305) — fallen auf member zurück.
  autor: 'Mitarbeiter (Autor)',
  manager: 'Mitarbeiter',
  user: 'Mitarbeiter',
};

export function roleLabel(role) {
  if (!role) return '';
  return ROLE_DE[role] || role;
}

export default roleLabel;
