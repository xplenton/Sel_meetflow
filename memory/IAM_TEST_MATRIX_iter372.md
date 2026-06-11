# IAM-Test-Matrix · MeetFlow Iter 372

## Skopus (Phase 4)
Vollständige Validierung (Frage 8a) für 4 System-Rollen × 67 Capabilities
+ Privilege-Escalation, IDOR, Direktzugriffe und Frontend/Backend-Drift.

## Test-Accounts (siehe `test_credentials.md`)
- `qa_admin@meetflow.com`     · qa_admin_pw_372
- `qa_moderator@meetflow.com` · qa_moderator_pw_372
- `qa_member@meetflow.com`    · qa_member_pw_372
- `qa_guest@meetflow.com`     · qa_guest_pw_372
- `newguest_1776557090@example.com` · qa_downgrade_pw_372 (RoleDowngradeBanner)

---

## 1. Erwartete Cap-Mengen pro Rolle (Soll-Werte)
| Rolle | Anzahl Caps | Wichtige Caps DRIN | Wichtige Caps NICHT DRIN |
|---|---|---|---|
| admin     | 67 | ALLE | (keine) |
| moderator | 44 | view:admin (durch Modul:Verwaltung), news.target_all, resources.approve, catering.process | admin.manage_users, admin.manage_groups, admin.manage_roles, admin.view_audit, invoices.set_accounting, users.view_drivers_license, resources.manage |
| member    | 19 | view:dashboard..tasks (durch Modul:Standard), resources.book, meetings.create, tasks.create | admin.*, news.approve, resources.approve, resources.manage, view:admin |
| guest     | 2 | view:dashboard, view:chat | alles andere |

## 2. Cap-zu-Endpoint-Mapping (Stichproben)
| Cap | Endpoint | Methode | Status erwartet |
|---|---|---|---|
| admin.manage_users | GET /api/admin/users | GET | 200 admin · 403 alle anderen |
| admin.manage_groups | POST /api/admin/groups | POST | 200 admin · 403 alle anderen |
| admin.manage_roles | GET /api/admin/capabilities | GET | 200 admin · 403 alle anderen |
| admin.view_audit | GET /api/admin/audit-log | GET | 200 admin · 403 alle anderen (auch moderator nach iter372) |
| resources.book | POST /api/resource-bookings | POST | 200 admin/moderator/member · 403 guest |
| resources.approve | POST /api/resource-bookings/{id}/approve | POST | 200 admin/moderator · 403 member/guest |
| resources.manage | POST /api/resources | POST | 200 admin · 403 alle anderen |
| view:resources | GET /api/resources | GET | 200 admin/moderator/member · 403 guest |
| catering.process | POST /api/catering-requests/{id}/process | POST | 200 admin/moderator · 403 member/guest |
| chat.broadcast | POST /api/chat/broadcast | POST | 200 admin · 403 alle anderen |
| users.view_drivers_license | GET /api/admin/users/{id}/drivers-license | GET | 200 admin · 403 alle anderen |
| invoices.create_manual | POST /api/invoices/manual | POST | 200 admin (kein moderator hat es) · 403 alle anderen |
| view:analytics | GET /api/analytics/* | GET | 200 admin/moderator · 403 member/guest |
| view:admin | GET /admin | (frontend) | sichtbar admin/moderator · versteckt member/guest |
| view:dashboard | GET /dashboard | (frontend) | alle |
| view:chat | GET /chat | (frontend) | alle |
| news.create | POST /api/news | POST | 200 admin/moderator · 403 member/guest |
| news.approve | POST /api/news/{id}/approve | POST | 200 admin/moderator · 403 member/guest |
| news.target_all | (Flag im News-Body) | POST | nur admin/moderator |
| meetings.create | POST /api/meetings | POST | 200 admin/moderator/member · 403 guest |
| tasks.create | POST /api/tasks | POST | 200 admin/moderator/member · 403 guest |
| surveys.create | POST /api/surveys | POST | 200 admin/moderator · 403 member/guest |

## 3. UI-Sichtbarkeit (Sidebar/Menü)
| Item | admin | moderator | member | guest |
|---|---|---|---|---|
| Dashboard      | ✓ | ✓ | ✓ | ✓ |
| News           | ✓ | ✓ | ✓ | ✗ |
| Umfragen       | ✓ | ✓ | ✓ | ✗ |
| Aufgaben       | ✓ | ✓ | ✓ | ✗ |
| Ressourcen     | ✓ | ✓ | ✓ | ✗ |
| Webkonferenz   | ✓ | ✓ | ✓ | ✗ |
| Terminplanung  | ✓ | ✓ | ✓ | ✗ |
| Chat           | ✓ | ✓ | ✓ | ✓ |
| Kalender       | ✓ | ✓ | ✓ | ✗ |
| Aufnahmen      | ✓ | ✓ | ✓ | ✗ |
| Verwaltung     | ✓ | ✓ (durch Modul:Verwaltung) | ✗ | ✗ |
| Auswertungen   | ✓ | ✓ (durch Modul:Auswertungen) | ✗ | ✗ |

## 4. Negativ-/Angriffstests
1. **Horizontal IDOR** — `member1` versucht `member2`s Buchung zu canceln (`DELETE /api/resource-bookings/{id_other}`). Erwartet: 403.
2. **Vertikale Privilege-Escalation** — `member` ruft `POST /api/admin/users/{eigene_id}` mit `role:"admin"` Body auf. Erwartet: 403 (Cap-Check) und Body-Strip.
3. **Token-Replay nach Rollenänderung** — Admin ändert `member`'s Rolle zu guest. Alte member-Tokens dieses Users müssen ungültig sein (token_version bump).
4. **Direkter API-Zugriff ohne Auth** — `GET /api/admin/users` ohne Header. Erwartet: 401.
5. **Direkter API-Zugriff mit manipuliertem Token** — Garbage-JWT. Erwartet: 401.
6. **Cap-Body-Stripping** — Member versucht `PUT /users/me` mit `role:"admin"`. Erwartet: ignoriert.
7. **Group-Override-Eskalation** — Member versucht sich selbst in `Modul: Verwaltung` einzutragen (`PUT /api/admin/groups/{verw}/members`). Erwartet: 403.
8. **Self-Delete der eigenen Admin-Rolle** — Admin versucht `DELETE /api/admin/users/{own_id}`. Erwartet: 400 (already implemented).
9. **License-Bypass** — Bei License-Status `invalid` muss `/api/resources/...` 503 zurückgeben. (Aktuell `disabled` in Preview → kein 503.)
10. **Cache-Stale nach Cap-Change** — Admin entzieht `resources.book` vom Member, nächster GET muss innerhalb 60 s die Änderung reflektieren (cache_invalidate).

## 5. Defense-in-Depth-Check
Backend muss UI-unabhängig prüfen:
- Jeder `/api/admin/*` Endpoint hat `if user.get('role') != 'admin'` oder `await require_cap(...)` ✓
- `cap_grants/cap_denies` mit `expires` werden geehrt
- Group-Removal cascade-cleant `user.groups`

## 6. Konsistenz-Reports
- API `GET /api/admin/users` ist auf 1000 limitiert → Hinweis ans Frontend (für Audit/Export `?page=N&limit=200` benutzen)
- After-Iter372 Soll-Werte sollten 0 stale group members ergeben (POST cleanup-stale-members aufrufen + Re-Count)
