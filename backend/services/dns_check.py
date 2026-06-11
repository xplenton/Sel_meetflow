"""
DNS verification helper for admins — checks MX, SPF (TXT), DKIM (resend._domainkey),
and DMARC for a given domain. Used by /api/admin/email-config/dns-check.

Never raises — returns structured ampel (✅/⚠️/❌) per record.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def _extract_domain(email_or_domain: str) -> str:
    s = (email_or_domain or "").strip().lower()
    if "@" in s:
        s = s.split("@", 1)[1]
    return s.strip(". ")


def _resolve_sync(domain: str, rtype: str) -> List[str]:
    import dns.resolver
    import dns.exception
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    resolver.timeout = 5.0
    try:
        answers = resolver.resolve(domain, rtype)
        out = []
        for r in answers:
            if rtype == "TXT":
                # Concatenate chunked TXT segments
                out.append("".join([s.decode() if isinstance(s, bytes) else s for s in r.strings]))
            elif rtype == "MX":
                out.append(f"{r.preference} {r.exchange.to_text().rstrip('.')}")
            else:
                out.append(r.to_text())
        return out
    except dns.resolver.NXDOMAIN:
        return []
    except dns.resolver.NoAnswer:
        return []
    except dns.exception.DNSException as e:
        logger.debug(f"DNS resolve {rtype} {domain} failed: {e}")
        return []


async def check_domain(email_or_domain: str, *, provider: str = "resend") -> Dict[str, Any]:
    """Return a structured ampel-report for the given domain.

    provider: hint for DKIM selector ('resend'|'sendgrid'|'generic').
    """
    domain = _extract_domain(email_or_domain)
    if not domain or "." not in domain:
        return {"domain": domain, "ok": False, "error": "invalid_domain"}

    # DKIM selector varies by provider
    dkim_selectors = {
        "resend": ["resend._domainkey"],
        "sendgrid": ["s1._domainkey", "s2._domainkey"],
        "generic": ["default._domainkey", "selector1._domainkey"],
    }.get(provider, ["resend._domainkey"])

    mx, spf_txts, dmarc_txts = await asyncio.gather(
        asyncio.to_thread(_resolve_sync, domain, "MX"),
        asyncio.to_thread(_resolve_sync, domain, "TXT"),
        asyncio.to_thread(_resolve_sync, f"_dmarc.{domain}", "TXT"),
    )
    dkim_results: List[Dict[str, Any]] = []
    for selector in dkim_selectors:
        full = f"{selector}.{domain}"
        records = await asyncio.to_thread(_resolve_sync, full, "TXT")
        dkim_results.append({"selector": selector, "host": full, "records": records, "ok": any("v=DKIM1" in r for r in records)})

    # SPF is a TXT entry starting with "v=spf1"
    spf_records = [t for t in spf_txts if t.lower().startswith("v=spf1")]
    dmarc_records = [t for t in dmarc_txts if t.lower().startswith("v=dmarc1")]

    mx_ok = len(mx) > 0
    spf_ok = len(spf_records) > 0
    dkim_ok = any(d["ok"] for d in dkim_results)
    dmarc_ok = len(dmarc_records) > 0

    severity = "ok" if (mx_ok and spf_ok and dkim_ok) else ("warn" if (mx_ok and (spf_ok or dkim_ok)) else "error")

    return {
        "domain": domain,
        "provider": provider,
        "mx": {"ok": mx_ok, "records": mx},
        "spf": {"ok": spf_ok, "records": spf_records, "all_txt": spf_txts},
        "dkim": {"ok": dkim_ok, "selectors": dkim_results},
        "dmarc": {"ok": dmarc_ok, "records": dmarc_records},
        "severity": severity,
        "summary": {
            "mx": "ok" if mx_ok else "error",
            "spf": "ok" if spf_ok else "error",
            "dkim": "ok" if dkim_ok else "error",
            "dmarc": "ok" if dmarc_ok else "warn",
        },
        "hints": _hints(provider, mx_ok, spf_ok, dkim_ok, dmarc_ok),
    }


def _hints(provider: str, mx: bool, spf: bool, dkim: bool, dmarc: bool) -> List[str]:
    hints: List[str] = []
    if not mx:
        hints.append("Keine MX-Records gefunden — für reinen Versand nicht zwingend, für Empfang aber noetig.")
    if not spf:
        if provider == "resend":
            hints.append("SPF fehlt. Erwarte TXT '@' = 'v=spf1 include:amazonses.com ~all' (Resend).")
        elif provider == "sendgrid":
            hints.append("SPF fehlt. Erwarte TXT '@' = 'v=spf1 include:sendgrid.net ~all'.")
        else:
            hints.append("SPF fehlt. Empfohlen: 'v=spf1 include:<provider> ~all'.")
    if not dkim:
        if provider == "resend":
            hints.append("DKIM fehlt. Resend zeigt CNAME 'resend._domainkey' in Dashboard › Domains.")
        elif provider == "sendgrid":
            hints.append("DKIM fehlt. SendGrid liefert 3 CNAMEs 's1,s2._domainkey' bei Domain-Authentication.")
        else:
            hints.append("DKIM fehlt. Selector wie 'default._domainkey' anlegen.")
    if not dmarc:
        hints.append("DMARC empfohlen: TXT '_dmarc' = 'v=DMARC1; p=none; rua=mailto:postmaster@<domain>'.")
    if mx and spf and dkim:
        hints.append("DNS sieht gut aus — DKIM-Propagation kann bis zu 24 h dauern.")
    return hints
