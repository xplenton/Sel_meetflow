"""
Capability-based permission system for MeetFlow.

- 4 System-Rollen: admin, moderator, member, guest
- ~30 granulare Capabilities mit deutschen UI-Labels
- Effektive Rechte = Rolle-Defaults ∪ Gruppen-Caps ∪ Direkt-Grants − Direkt-Denies
- Backwards-compatible: alte Rollen werden im `migrate_user_role` gemappt
"""
from typing import Iterable
from fastapi import HTTPException

# ============ CAPABILITY REGISTRY ============
# (key, category, german_label, description)
CAPABILITIES = [
    # --- Module-Sichtbarkeit ---
    ("view:dashboard", "module", "Dashboard", "Zugriff auf Start-Dashboard"),
    ("view:news", "module", "News", "News-Modul sehen"),
    ("view:chat", "module", "Chat", "Chat-Modul sehen"),
    ("view:meetings", "module", "Meetings", "Webkonferenzen sehen"),
    ("view:scheduling", "module", "Terminplanung", "Terminumfragen und -planung"),
    ("view:calendar", "module", "Kalender", "Kalender sehen"),
    ("view:recordings", "module", "Aufnahmen", "Meeting-Aufnahmen sehen"),
    ("view:surveys", "module", "Umfragen", "Umfragen-Modul sehen"),
    ("view:tasks", "module", "Aufgaben", "Aufgaben-Modul (Kanban/Liste/Kalender)"),
    ("view:filetransfer", "module", "Filetransfer", "Filetransfer-Modul sehen"),
    ("view:admin", "module", "Verwaltung", "Admin-Bereich sehen"),
    ("view:analytics", "module", "Auswertungen", "Analytics-Reports sehen"),

    # --- News & Kommunikation ---
    ("news.create", "news", "News erstellen", "Neue Beitraege anlegen (Entwurf)"),
    ("news.review", "news", "News prüfen", "Beitraege zur Freigabe prüfen"),
    ("news.approve", "news", "News freigeben", "Beitraege freigeben und veroeffentlichen"),
    ("news.publish", "news", "News veroeffentlichen", "Direkt veroeffentlichen (ohne Review)"),
    ("news.moderate", "news", "News moderieren", "Beitraege/Kommentare melden bearbeiten"),
    ("news.pin", "news", "News anpinnen", "Beitraege oben im Feed anpinnen"),
    ("news.target_all", "news", "An alle zielgruppieren", "Beitraege an gesamte Organisation"),
    ("news.mandatory", "news", "Pflicht-Lesebestaetigung", "Beitraege als Pflichtlese markieren"),

    # --- Meetings ---
    ("meetings.create", "meetings", "Meetings erstellen", "Webkonferenzen planen/starten"),
    ("meetings.record", "meetings", "Meetings aufnehmen", "Aufnahmen starten waehrend Meeting"),
    ("meetings.invite_external", "meetings", "Externe einladen", "Gaeste mit externer E-Mail einladen"),
    ("meetings.manage_others", "meetings", "Fremde Meetings verwalten", "Meetings anderer Nutzer bearbeiten/löschen"),
    ("meetings.delete_recordings", "meetings", "Aufnahmen löschen", "Meeting-Aufnahmen endgueltig löschen"),
    ("meetings.view_attendance", "meetings", "Teilnahmestatistik", "Attendance Reports einsehen"),

    # --- Chat ---
    ("chat.create_group", "chat", "Chat-Gruppe erstellen", "Neue Gruppen-Chats anlegen"),
    ("chat.delete_messages", "chat", "Nachrichten moderieren", "Fremde Nachrichten löschen"),
    ("chat.broadcast", "chat", "Broadcast senden", "Nachrichten an alle Nutzer senden"),

    # --- Documents & Whiteboard ---
    ("documents.upload", "documents", "Dokumente hochladen", "Dateien in den Dokumentenbereich hochladen"),
    ("documents.delete_others", "documents", "Fremde Dokumente löschen", "Dokumente anderer Nutzer löschen"),
    ("whiteboard.create", "documents", "Whiteboard erstellen", "Neues Whiteboard anlegen"),
    ("whiteboard.delete_others", "documents", "Fremde Whiteboards löschen", "Whiteboards anderer löschen"),

    # --- Scheduling ---
    ("scheduling.create_poll", "scheduling", "Terminumfrage erstellen", "Terminumfragen für Meetings anlegen"),
    ("scheduling.delete_others", "scheduling", "Fremde Termine löschen", "Terminumfragen anderer löschen"),

    # --- Umfragen ---
    ("surveys.create", "surveys", "Umfragen erstellen", "Umfragen und Pulse-Checks anlegen"),
    ("surveys.view_results", "surveys", "Ergebnisse sehen", "Umfrageergebnisse aller Teilnehmer"),
    ("surveys.export", "surveys", "Ergebnisse exportieren", "CSV/PDF-Exports erstellen"),
    ("surveys.view_anonymous", "surveys", "Anonyme Antworten sehen", "Auch anonyme Antworten einsehen"),

    # --- Aufgabenmanagement ---
    ("tasks.create", "tasks", "Aufgaben erstellen", "Neue Aufgaben (Tasks) anlegen"),
    ("tasks.assign_others", "tasks", "Andere zuweisen", "Aufgaben fremden Nutzern oder Gruppen zuweisen"),
    ("tasks.view_all", "tasks", "Alle Aufgaben sehen", "Filter 'Alle Verantwortlichen' verfügbar (sonst nur eigene)"),
    # Iter 377 — Aufgaben aus der eigenen Abteilung mitsehen (z.B. Stations-/
    # Kuechenleitung). Schwaecher als `view_all`, staerker als nur-eigene.
    ("tasks.view_department", "tasks", "Aufgaben Abteilung sehen", "Aufgaben aller Mitarbeiter der eigenen Abteilung mitsehen"),
    ("tasks.delete_others", "tasks", "Fremde Aufgaben löschen", "Aufgaben anderer Nutzer löschen"),
    ("tasks.export", "tasks", "Aufgaben exportieren", "Aufgabenlisten als CSV exportieren"),

    # --- Ressourcen-Buchung (iter 223) ---
    ("view:resources", "module", "Ressourcen", "Buchungs-Modul (Raume/Desks/Fahrzeuge)"),
    ("resources.book", "resources", "Ressource buchen", "Eigene Buchungen anlegen"),
    ("resources.book_for_others", "resources", "Für andere buchen", "Buchungen für andere Nutzer/Teams"),
    ("resources.manage", "resources", "Ressourcen verwalten", "Stammdaten Raum/Desk/Fahrzeug pflegen"),
    ("resources.approve", "resources", "Genehmigungspflichtige freigeben", "Buchungen mit Genehmigungspflicht freigeben"),
    ("resources.view_all_bookings", "resources", "Alle Buchungen sehen", "Buchungen anderer Nutzer einsehen"),
    ("catering.manage_items", "resources", "Catering-Artikel pflegen", "Verpflegungs-Stammdaten pflegen"),
    ("catering.process", "resources", "Catering bearbeiten", "Anfragen bestätigen/ablehnen/bereitstellen"),
    ("bookings.invoice", "resources", "Buchungen abrechnen", "Interne Verrechnung/Rechnungen erstellen"),
    ("bookings.invoice.approve", "resources", "Rechnungen freigeben", "Erstellte Rechnungen genehmigen, versenden, stornieren"),

    # --- Admin ---
    ("admin.manage_users", "admin", "Nutzer verwalten", "Nutzer einladen/ändern/löschen"),
    ("admin.manage_groups", "admin", "Gruppen verwalten", "Gruppen anlegen/ändern"),
    ("admin.manage_policies", "admin", "Richtlinien verwalten", "Meeting-Richtlinien"),
    ("admin.manage_branding", "admin", "Branding verwalten", "Logo/Farben/Design"),
    ("admin.manage_integrations", "admin", "Integrationen verwalten", "API-Keys LLM/E-Mail"),
    ("admin.manage_roles", "admin", "Rollen & Rechte verwalten", "Capability-Matrix bearbeiten"),
    ("admin.view_audit", "admin", "Audit-Log sehen", "System-Audit einsehen"),

    # --- Fuhrpark / Führerschein (iter 292) ---
    ("users.view_drivers_license", "fleet", "Führerscheine anderer sehen", "Eingetragene Führerscheine + Fotos aller Nutzer einsehen (Fuhrpark-Manager)"),

    # --- Auswertungen / Reporting (iter 397/398) ---
    # Granulare Tab-Level-Capabilities, sodass Admins z.B. Buchhaltung nur
    # auf Catering-Historie, Fuhrpark-Manager nur auf Führerscheine etc.
    # berechtigen koennen.
    ("analytics.view_meetings", "analytics", "Meeting-Auswertung sehen", "Meeting-Statistiken (Daily, Top-User, Attendance) im Tab Meetings einsehen"),
    ("analytics.view_scheduling", "analytics", "Terminplanungs-Auswertung sehen", "Terminplanungs-Aktivitaeten und Slot-Auslastung einsehen"),
    ("analytics.view_surveys", "analytics", "Umfragen-Auswertung sehen", "Umfragen-Ergebnisse und Teilnahmequoten einsehen"),
    ("analytics.view_bookings", "analytics", "Buchungs-Auswertung sehen", "Ressourcen-Buchungen und Auslastung einsehen"),
    ("analytics.view_platform_stats", "analytics", "Plattform-Statistiken sehen", "Gesamtzahlen (Nutzer, Meetings, Nachrichten, Umfragen) einsehen"),
    ("analytics.view_catering_history", "analytics", "Catering-Historie sehen", "Verbrauchte Catering-Artikel mit Buchung, Kostenstelle und Rechnungsstatus einsehen (mit CSV-Export)"),

    # --- Rechnungs-Konfiguration (iter 293) ---
    ("invoices.manage_templates", "invoices", "Rechnungsvorlagen verwalten", "Layout, Pflichtfelder, Header/Footer, Zahlungsbedingungen"),
    ("invoices.manage_master_data", "invoices", "Rechnungs-Stammdaten verwalten", "Konten, Kostenstellen, Kostenträger, Projekte, Nummernkreise"),
    ("invoices.create_manual", "invoices", "Manuelle Rechnung erstellen", "Freie Rechnung mit eigenen Positionen erstellen (ohne Buchungs-Aggregat)"),
    ("invoices.set_accounting", "invoices", "Buchhalterische Zuordnung ändern", "Konto/Kostenstelle/Kostenträger nachträglich anpassen (Buchhaltung)"),

    # --- Global ---
    ("export.data", "global", "Daten exportieren", "Generelle Export-Rechte (Interaktionen etc.)"),
    ("attachments.delete_others", "global", "Fremde Anhaenge löschen", "Attachments anderer Nutzer löschen"),

    # --- Filetransfer (iter 386) ---
    ("filetransfer.use", "filetransfer", "Filetransfer nutzen", "Dateien hochladen, intern teilen und externe Links erstellen"),
    ("filetransfer.admin", "filetransfer", "Filetransfer administrieren", "Speicher-/Verschlüsselungs-Einstellungen + Übersicht aller Transfers"),
]

CAPABILITY_KEYS = {c[0] for c in CAPABILITIES}

# ============ ROLE DEFAULTS ============
# System roles after migration: admin, moderator, member, guest
#
# Iter 306 (Variante C) — `view:*` capabilities are NO LONGER part of role
# defaults. Module visibility is now controlled exclusively via the four
# system-managed module groups (see routes/org_onboarding.py):
#   - "Modul: Gast"        → view:dashboard, view:chat
#   - "Modul: Standard"    → all member-level modules
#   - "Modul: Verwaltung"  → view:admin
#   - "Modul: Auswertungen"→ view:analytics
# Every user is auto-synced into the right module groups for their role on
# startup and on every role change. Admin role still includes view:* via
# CAPABILITY_KEYS (admin gets EVERYTHING).
ROLE_DEFAULTS = {
    "admin": set(CAPABILITY_KEYS),  # All caps — includes view:* as a safety net
    "moderator": {
        "news.create", "news.review", "news.approve", "news.publish",
        "news.moderate", "news.pin", "news.target_all", "news.mandatory",
        "meetings.create", "meetings.record", "meetings.invite_external",
        "meetings.view_attendance",
        "chat.create_group", "chat.delete_messages",
        "documents.upload", "whiteboard.create",
        "scheduling.create_poll",
        "surveys.create", "surveys.view_results", "surveys.export", "surveys.view_anonymous",
        "tasks.create", "tasks.assign_others", "tasks.view_all", "tasks.delete_others", "tasks.export",
        # Iter 372 — `admin.view_audit` aus Moderator-Defaults entfernt.
        # Audit-Log ist Admin-Level. Falls einzelne Moderatoren Audit sehen
        # sollen, kann der Admin die Cap direkt per cap_grants setzen.
        # Iter 240 — Ressourcen: Moderator darf alle Buchungen sehen, freigeben,
        # canceln und Catering verarbeiten. Keine Stammdaten-Konfiguration (manage).
        # Iter 370 — Ghost-Caps (`book_with_approval`, `cancel_any`,
        # `process_catering`) entfernt; nirgendwo in der Codebase abgefragt.
        # Tatsaechliche Caps fuer dieselbe Funktion: `resources.approve`,
        # `resources.view_all_bookings`, `catering.process`.
        "resources.book", "resources.approve", "resources.view_all_bookings",
        "catering.process",
        "filetransfer.use",
        "export.data", "attachments.delete_others",
    },
    "member": {
        # Iter 380 — Rollen-Rechte-Matrix exakt an "Mitarbeiter Standard"-
        # Preset-Gruppe ausgerichtet. Keine zusaetzlichen Rechte mehr, die
        # nicht auch in der Gruppe sind:
        #   * KEIN meetings.create (Meetings nur fuer Moderator/Admin)
        #   * KEIN surveys.view_results (Umfragen-Auswertung nur Moderator)
        #   * KEIN documents.upload (Dokumente nur Moderator)
        #   * KEIN whiteboard.create (Whiteboards nur Moderator)
        #   * KEIN tasks.assign_others (nur eigene Tasks + Abteilungs-Tasks lesen)
        #
        # Die View-Module (`view:dashboard`, `view:tasks`, ...) werden NICHT
        # ueber ROLE_DEFAULTS gesetzt — sie kommen aus DEFAULT_MODULES je
        # Rolle (siehe `compute_user_module_groups` weiter unten). Hier sind
        # nur die *Aktions*-Caps relevant.
        "tasks.create", "tasks.view_department",
        "resources.book", "resources.book_for_others",
        "chat.create_group",
        "scheduling.create_poll",
        # Iter 386 — Standard-Member darf Filetransfer nutzen.
        "filetransfer.use",
    },
    "guest": set(),
}

# ============ LEGACY ROLE MIGRATION ============
LEGACY_ROLE_MAP = {
    "redakteur": ("moderator", ["news.create", "news.review", "news.moderate", "news.pin"]),
    "freigeber": ("moderator", ["news.approve", "news.publish"]),
    "autor": ("member", ["news.create"]),
    "manager": ("member", []),
    "user": ("member", []),
    # host / co-host stay — they are meeting-level, not system-level
}


def migrate_role(old_role: str) -> str:
    """Map a legacy role to a new system role. Returns one of admin/moderator/member/guest."""
    if old_role in ("admin", "moderator", "member", "guest"):
        return old_role
    if old_role in LEGACY_ROLE_MAP:
        return LEGACY_ROLE_MAP[old_role][0]
    return "member"  # unknown legacy role defaults to member


def extra_grants_for_legacy(old_role: str) -> list:
    """Return extra capabilities to attach to user based on their legacy role."""
    if old_role in LEGACY_ROLE_MAP:
        return LEGACY_ROLE_MAP[old_role][1]
    return []


# ============ CAPABILITY RESOLUTION ============

def _resolve_from_user(user: dict) -> set:
    """Compute effective capability set from user document + their groups (pre-loaded).
    Respects expiration timestamps in user['cap_expires'] — expired grants/denies are ignored.

    Iter 289 — Group `role_override`: if any of the user's groups carries a
    role_override (e.g. the "Gast"-group sets `role_override='guest'`), the
    *lowest* override wins and downgrades the user's effective base role.
    Without this, assigning a guest-group to a user with role=member would
    still leave the user with all member-level view caps (sidebar showed
    every menu item, against the admin's intent).
    """
    from datetime import datetime as _dt, timezone as _tz
    role = user.get("role", "member")
    role = migrate_role(role)

    # Determine lowest role across user.role + group role_overrides
    # Iter 289 — Admins are NEVER downgraded by group role_override, regardless
    # of group assignments. This prevents an admin from accidentally losing
    # access to their own admin tools by being added to a "Gast" group.
    ROLE_RANK = {"guest": 0, "member": 1, "moderator": 2, "admin": 3}
    groups = user.get("_groups", []) or []
    if role == "admin":
        effective_role = "admin"
    else:
        candidate_roles = [role]
        for gr in groups:
            ov = (gr.get("role_override") or "").strip().lower()
            if ov in ROLE_RANK:
                candidate_roles.append(ov)
        # Pick the role with the lowest rank (i.e. most restrictive)
        effective_role = min(candidate_roles, key=lambda r: ROLE_RANK.get(r, 99))

    caps = set(ROLE_DEFAULTS.get(effective_role, set()))

    expires = user.get("cap_expires", {}) or {}
    now = _dt.now(_tz.utc)

    def _is_active(cap):
        exp = expires.get(cap)
        if not exp:
            return True
        try:
            dt = _dt.fromisoformat(exp.replace("Z", "+00:00")) if isinstance(exp, str) else None
            if not dt:
                return True
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            return now < dt
        except (ValueError, AttributeError):
            return True

    # iter 213 — Bug fix: collect all positive sources FIRST, then apply denies
    # at the very end. The previous order added group caps AFTER denies, which
    # meant a deny on a group-granted capability silently failed (the group
    # immediately re-added it). That broke the documented security guarantee
    # that admin denies override every other source.
    for g in user.get("cap_grants", []) or []:
        if _is_active(g):
            caps.add(g)

    for gr in user.get("_groups", []) or []:
        caps |= set(gr.get("capabilities", []) or [])

    for d in user.get("cap_denies", []) or []:
        if _is_active(d):
            caps.discard(d)

    return caps


# ============ CAPABILITY PRESETS ============
# One-Click capability sets for common clinic roles.
# Iter 375 — Audit-Pass: jedes Preset enthaelt jetzt die `view:*` Module,
# die fuer die Action-Caps tatsaechlich benoetigt werden (Self-Contained).
# So funktioniert ein Preset auch dann, wenn der User KEINE Member-Defaults
# durch `Modul: Standard` mitbringt (z.B. wenn er auf Guest downgegradet ist).
PRESETS = [
    {
        "preset_id": "news_editor",
        "label": "News-Redakteur",
        "description": "Kann News anlegen, prüfen, moderieren und anpinnen",
        "capabilities": [
            "view:news",
            "news.create", "news.review", "news.moderate", "news.pin",
        ],
    },
    {
        "preset_id": "news_approver",
        "label": "News-Freigeber",
        "description": "Kann News freigeben und veroeffentlichen",
        "capabilities": [
            "view:news",
            "news.approve", "news.publish", "news.mandatory",
        ],
    },
    {
        "preset_id": "station_lead",
        "label": "Stations-Leitung",
        "description": "Mitarbeiter mit erweiterten Rechten (News, Umfrage-Ergebnisse, Anhaenge)",
        "capabilities": [
            "view:news", "view:surveys", "view:meetings",
            "news.create", "surveys.view_results", "surveys.export",
            "attachments.delete_others", "meetings.record",
        ],
    },
    {
        "preset_id": "external_doctor",
        "label": "Externer Arzt",
        "description": "Extern + eingeschraenkter Modul-Zugang (Meetings, Kalender)",
        "capabilities": [
            "view:dashboard", "view:meetings", "view:calendar", "view:chat",
            "meetings.create", "meetings.invite_external",
        ],
    },
    {
        "preset_id": "read_only_guest",
        "label": "Nur-Lese-Gast",
        "description": "Nur Ansicht - News und Chat, keine Aktionen",
        "capabilities": ["view:dashboard", "view:news", "view:chat"],
    },
    {
        "preset_id": "analytics_viewer",
        "label": "Auswertungen",
        "description": "Darf Reports, Analytics, Ressourcen-Auslastung und Exports sehen",
        "capabilities": [
            "view:analytics", "view:surveys", "view:resources",
            "export.data", "surveys.export", "surveys.view_results",
            # Sprint 4 — Resource analytics + invoice review
            "resources.view_all_bookings", "bookings.invoice",
        ],
    },
    {
        "preset_id": "survey_creator",
        "label": "Umfragen-Ersteller",
        "description": "Kann Umfragen anlegen und Ergebnisse exportieren",
        "capabilities": [
            "view:surveys",
            "surveys.create", "surveys.view_results", "surveys.export",
        ],
    },
    {
        "preset_id": "nursing_lead",
        "label": "Pflegedienstleitung",
        "description": "PDL: News, Umfragen, Terminumfragen, Anhaenge — darf Raeume und Desks für Team buchen",
        "capabilities": [
            "view:news", "view:surveys", "view:scheduling", "view:meetings", "view:resources",
            "news.create", "news.review", "news.pin",
            "surveys.create", "surveys.view_results", "surveys.export",
            "attachments.delete_others", "scheduling.create_poll",
            "meetings.view_attendance",
            # Sprint 4 — Resource booking caps
            "resources.book", "resources.book_for_others",
        ],
    },
    {
        "preset_id": "department_head",
        "label": "Abteilungsleiter",
        "description": "Chef-/Oberarzt mit erweiterten News/Meetings/Reporting-Rechten — darf Raeume genehmigen und Rechnungen einsehen",
        "capabilities": [
            "view:news", "view:meetings", "view:surveys", "view:analytics", "view:resources",
            "news.create", "news.review", "news.approve", "news.pin", "news.mandatory",
            "meetings.record", "meetings.invite_external", "meetings.view_attendance",
            "surveys.create", "surveys.view_results", "surveys.export",
            "export.data",
            # Sprint 4 — Resource booking caps
            "resources.book", "resources.book_for_others",
            "resources.approve", "resources.view_all_bookings",
            "bookings.invoice", "bookings.invoice.approve",
        ],
    },
    {
        "preset_id": "it_support",
        "label": "IT-Support",
        "description": "Technische Admin-Rechte ohne Personalverwaltung",
        "capabilities": [
            "view:admin", "view:analytics",
            "admin.manage_integrations", "admin.manage_policies",
            "admin.manage_branding", "admin.view_audit",
        ],
    },
    {
        "preset_id": "data_protection",
        "label": "Datenschutzbeauftragter",
        "description": "Audit, Export und anonyme Umfrage-Einsicht",
        "capabilities": [
            "view:admin", "view:analytics", "view:surveys",
            "admin.view_audit", "export.data",
            "surveys.view_anonymous", "surveys.view_results", "surveys.export",
        ],
    },
    {
        "preset_id": "intern",
        "label": "Praktikant / Auszubildender",
        "description": "Sehr eingeschraenkt: Nur Lesen und Chat",
        "capabilities": [
            "view:dashboard", "view:news", "view:chat", "view:meetings", "view:calendar",
        ],
    },
    {
        "preset_id": "broadcast_admin",
        "label": "Kommunikations-Admin",
        "description": "Darf Broadcasts und Pflicht-News senden",
        "capabilities": [
            "view:news", "view:chat", "view:admin",
            "news.create", "news.approve", "news.publish",
            "news.mandatory", "news.target_all",
            "chat.broadcast",
        ],
    },
    # ------------------------------------------------------------------
    # Sprint 4 — Resource-module specialist roles (iter 226 consolidation)
    # ------------------------------------------------------------------
    {
        "preset_id": "catering_lead",
        "label": "Catering-Verantwortliche",
        "description": "Pflegt Catering-Artikel, bestätigt/lehnt Catering-Anfragen ab und arbeitet Catering-Aufgaben ab",
        "capabilities": [
            "view:resources", "view:tasks",
            "resources.book",
            "catering.manage_items", "catering.process",
        ],
    },
    {
        "preset_id": "fleet_manager",
        "label": "Fuhrparkverantwortliche",
        "description": "Verwaltet Fahrzeug-Stammdaten, sieht alle Fahrzeug-Buchungen, genehmigt Sonderfahrten",
        "capabilities": [
            "view:resources",
            "resources.book", "resources.book_for_others",
            "resources.manage", "resources.approve", "resources.view_all_bookings",
            "bookings.invoice", "bookings.invoice.approve",
        ],
    },
    {
        "preset_id": "facility_manager",
        "label": "Facility-/Hausmanagement",
        "description": "Pflegt Raum-/Desk-Stammdaten und Catering-Artikel, sieht Auslastung",
        "capabilities": [
            "view:resources", "view:analytics",
            "resources.book", "resources.book_for_others",
            "resources.manage", "resources.view_all_bookings",
            "catering.manage_items",
        ],
    },
]


def get_preset(preset_id: str):
    for p in PRESETS:
        if p["preset_id"] == preset_id:
            return p
    return None


async def get_effective_capabilities(user: dict, db) -> set:
    """Load user's groups and compute effective capabilities."""
    group_ids = user.get("groups", []) or []
    if group_ids:
        groups = await db.groups.find(
            {"group_id": {"$in": group_ids}},
            # Iter 289 — Also fetch role_override so _resolve_from_user can
            # downgrade the user's effective base role.
            {"_id": 0, "capabilities": 1, "role_override": 1},
        ).to_list(50)
        user["_groups"] = groups
    return _resolve_from_user(user)


async def has_cap(user: dict, cap: str, db) -> bool:
    """Check if user has a specific capability. Loads groups lazily."""
    if cap not in CAPABILITY_KEYS:
        raise ValueError(f"Unknown capability: {cap}")
    if "_caps_cache" in user:
        return cap in user["_caps_cache"]
    caps = await get_effective_capabilities(user, db)
    user["_caps_cache"] = caps
    return cap in caps


async def require_cap(user: dict, cap: str, db):
    """Raise 403 if user lacks the capability."""
    if not await has_cap(user, cap, db):
        raise HTTPException(status_code=403, detail=f"Fehlende Berechtigung: {cap}")


async def require_any(user: dict, caps: Iterable[str], db):
    """Raise 403 if user has none of the given capabilities."""
    for c in caps:
        if await has_cap(user, c, db):
            return
    raise HTTPException(status_code=403, detail="Keine Berechtigung")
