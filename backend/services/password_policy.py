"""Iter 379 — Password Policy Service.

Zentrale Implementierung der Passwort-Richtlinie:

* Mindestlaenge: 8 Zeichen
* 4-aus-4-Regel: mindestens je ein
    - Grossbuchstabe (A-Z)
    - Kleinbuchstabe (a-z)
    - Ziffer (0-9)
    - Sonderzeichen (!@#$...)
* Passwort-Historie: letzte N Hashes (default 3) duerfen nicht wiederverwendet werden
* Passwort-Rotation: konfigurierbar in Monaten ueber `org_settings.password_rotation_months`
    - 0 = deaktiviert
    - default: 6 Monate
    - >0  = beim Login wird `must_change_password=True` gesetzt wenn ueberschritten

Verwendet wird die Policy:
* Beim POST /auth/register
* Beim POST /auth/change-password
* Beim Admin-gesetzten Initialpasswort (Invite-Flow + Force-Set)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Iterable

from fastapi import HTTPException

# Mindestlaenge in Zeichen
PW_MIN_LENGTH = 8
# Anzahl historischer Hashes, die nicht erneut verwendet werden duerfen.
PW_HISTORY_SIZE = 3
# Default Rotationszeit in Monaten (0 = deaktiviert).
PW_DEFAULT_ROTATION_MONTHS = 6

_SPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};:'\",.<>/?\\|`~]")


def password_policy_meta() -> dict:
    """Beschreibt die aktuelle Policy in Form, die das Frontend rendern kann."""
    return {
        "min_length": PW_MIN_LENGTH,
        "requires_upper": True,
        "requires_lower": True,
        "requires_digit": True,
        "requires_special": True,
        "history_size": PW_HISTORY_SIZE,
        "rotation_months_default": PW_DEFAULT_ROTATION_MONTHS,
    }


def evaluate_password(password: str) -> dict:
    """Wertet die Kriterien einzeln aus — fuer Live-Validierung im Frontend.

    Backend nutzt das auch um sehr aussagekraeftige Fehlermeldungen zu erzeugen.
    """
    p = password or ""
    return {
        "length_ok":   len(p) >= PW_MIN_LENGTH,
        "has_upper":   bool(re.search(r"[A-Z]", p)),
        "has_lower":   bool(re.search(r"[a-z]", p)),
        "has_digit":   bool(re.search(r"\d", p)),
        "has_special": bool(_SPECIAL.search(p)),
    }


def validate_password_or_raise(password: str) -> None:
    """Validiert das Passwort gegen die 4-aus-4-Regel + Mindestlaenge.

    Wirft HTTPException(400) mit deutscher Fehlermeldung wenn die Policy
    verletzt wird. Liste der nicht erfuellten Kriterien wird mitgeliefert,
    damit die UI alles auf einmal anzeigen kann.
    """
    ev = evaluate_password(password)
    fails = []
    if not ev["length_ok"]:
        fails.append(f"mindestens {PW_MIN_LENGTH} Zeichen")
    if not ev["has_upper"]:
        fails.append("mindestens einen Grossbuchstaben")
    if not ev["has_lower"]:
        fails.append("mindestens einen Kleinbuchstaben")
    if not ev["has_digit"]:
        fails.append("mindestens eine Ziffer")
    if not ev["has_special"]:
        fails.append("mindestens ein Sonderzeichen")
    if fails:
        raise HTTPException(
            status_code=400,
            detail="Passwort entspricht nicht der Richtlinie: " + ", ".join(fails) + ".",
        )


def check_history_or_raise(new_password: str, history_hashes: Iterable[str], verify_fn) -> None:
    """Stellt sicher, dass `new_password` keinem der letzten N Hashes
    entspricht. `verify_fn(plain, hashed) -> bool` wird vom Aufrufer
    durchgereicht (in der Regel `dependencies.verify_password`).
    """
    for h in history_hashes or []:
        if not h:
            continue
        try:
            if verify_fn(new_password, h):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Neues Passwort darf nicht mit einem der letzten "
                        f"{PW_HISTORY_SIZE} Passwoerter übereinstimmen."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            # Defekter Hash in Historie (z.B. nach Hash-Algo-Upgrade) -> skip
            continue


def push_password_history(history: list | None, old_hash: str) -> list:
    """Haengt `old_hash` an die Historie an und kuerzt auf PW_HISTORY_SIZE."""
    if not old_hash:
        return list(history or [])
    new = list(history or [])
    new.append(old_hash)
    # Nur die N letzten behalten (FIFO, neueste am Ende).
    return new[-PW_HISTORY_SIZE:]


async def is_password_rotation_due(user: dict, settings_doc: dict | None = None) -> bool:
    """True, wenn das Passwort des Users laut Org-Setting wieder gesetzt werden muss.

    `settings_doc` darf vom Aufrufer durchgereicht werden, um einen zweiten
    DB-Roundtrip zu vermeiden. Andernfalls wird `org_settings` einmal gelesen.
    """
    if user.get("must_change_password"):
        return True
    # Resolve Rotations-Einstellung
    months = None
    if settings_doc is not None:
        months = settings_doc.get("password_rotation_months")
    if months is None:
        # local import to avoid circular at module import time
        from database import db
        doc = await db.org_settings.find_one({}, {"_id": 0, "password_rotation_months": 1})
        months = (doc or {}).get("password_rotation_months", PW_DEFAULT_ROTATION_MONTHS)
    try:
        months = int(months)
    except Exception:
        months = PW_DEFAULT_ROTATION_MONTHS
    if months <= 0:
        return False
    changed_at = user.get("password_changed_at")
    if not changed_at:
        # Iter 379 — Legacy-User ohne `password_changed_at` (alle Accounts, die
        # vor Einfuehrung der Rotation existierten) NICHT zwanghaft zum Wechsel
        # zwingen. Wir behandeln sie so, als haetten sie das Passwort genau
        # jetzt gesetzt — bei der naechsten echten Aenderung wird der
        # Timestamp gesetzt und die Rotation greift dann ab da.
        return False
    try:
        if isinstance(changed_at, str):
            changed_at = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    # 1 Monat = ~30 Tage. Bewusst grosszuegig — Compliance-Zielwert, kein Sekunden-genau-SLA.
    return datetime.now(timezone.utc) - changed_at > timedelta(days=30 * months)
