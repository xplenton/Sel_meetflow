"""
Branded HTML e-mail templates for MeetFlow (iter 227).

A single `render_email()` helper wraps any content into a consistent header,
spacing, footer and call-to-action button. Used by the resource module's
catering / approval / reminder mailings and re-usable across the platform.

Design tokens are kept in-line because most e-mail clients ignore <link>/<style>
in <head>; everything is inlined for maximum compatibility.
"""
from typing import Optional


BRAND_PRIMARY = "#4A5D4E"   # MeetFlow green
BRAND_ACCENT = "#C87967"    # warm coral for important highlights
BRAND_TEXT = "#1C1F1D"
BRAND_MUTED = "#6B7280"
BRAND_BORDER = "#E2E4E0"
BRAND_BG = "#FAFBF9"


def render_email(
    *,
    title: str,
    preheader: str = "",
    body_html: str,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    footer_note: str = "",
    accent: bool = False,
) -> str:
    """Wrap content into a polished, mobile-friendly e-mail template."""
    accent_color = BRAND_ACCENT if accent else BRAND_PRIMARY
    cta_block = ""
    if cta_label and cta_url:
        cta_block = f"""
        <tr><td style="padding:8px 32px 24px 32px;">
          <a href="{cta_url}" target="_blank"
             style="display:inline-block;padding:12px 24px;border-radius:8px;
                    background:{accent_color};color:#ffffff;text-decoration:none;
                    font-weight:600;font-family:Manrope,Helvetica,Arial,sans-serif;
                    font-size:14px;letter-spacing:0.01em;">
            {cta_label}
          </a>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light only">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{BRAND_BG};
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Manrope,Helvetica,Arial,sans-serif;
             color:{BRAND_TEXT};">
  <span style="display:none !important;color:transparent;height:0;width:0;overflow:hidden;">
    {preheader}
  </span>
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
         style="background:{BRAND_BG};padding:24px 16px;">
    <tr><td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" width="600"
             style="max-width:600px;width:100%;background:#ffffff;
                    border:1px solid {BRAND_BORDER};border-radius:12px;
                    overflow:hidden;">
        <tr>
          <td style="background:{accent_color};padding:18px 32px;">
            <div style="font-family:Manrope,Helvetica,Arial,sans-serif;
                        color:#ffffff;font-size:18px;font-weight:700;
                        letter-spacing:0.01em;">
              MeetFlow
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 32px 8px 32px;">
            <h1 style="margin:0 0 12px 0;font-family:Manrope,Helvetica,Arial,sans-serif;
                       font-size:22px;font-weight:700;line-height:1.3;
                       color:{BRAND_TEXT};">
              {title}
            </h1>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 16px 32px;font-size:14px;line-height:1.6;
                     color:{BRAND_TEXT};">
            {body_html}
          </td>
        </tr>
        {cta_block}
        <tr>
          <td style="padding:0 32px 24px 32px;border-top:1px solid {BRAND_BORDER};">
            <p style="margin:16px 0 0 0;font-size:11px;color:{BRAND_MUTED};
                      line-height:1.5;">
              {footer_note or 'Du erhaeltst diese E-Mail weil du in MeetFlow registriert bist. Einstellungen kannst du in deinem Profil anpassen.'}
            </p>
          </td>
        </tr>
      </table>
      <div style="padding-top:12px;font-size:11px;color:{BRAND_MUTED};">
        MeetFlow &middot; <a href="https://www.meetflow.app" style="color:{BRAND_MUTED};text-decoration:none;">meetflow.app</a>
      </div>
    </td></tr>
  </table>
</body>
</html>"""


def render_kv_list(items: list) -> str:
    """Render a key/value list as a polished table for e-mails.
    items: [(label, value), ...]
    """
    rows = []
    for label, value in items:
        if value is None or value == "":
            continue
        rows.append(f"""
          <tr>
            <td style="padding:6px 12px 6px 0;color:{BRAND_MUTED};
                       font-size:12px;width:35%;vertical-align:top;">{label}</td>
            <td style="padding:6px 0;color:{BRAND_TEXT};
                       font-size:13px;font-weight:500;vertical-align:top;">{value}</td>
          </tr>""")
    return f"""<table role="presentation" cellpadding="0" cellspacing="0"
                style="width:100%;border-top:1px solid {BRAND_BORDER};
                       border-bottom:1px solid {BRAND_BORDER};margin:8px 0;">
      {''.join(rows)}
    </table>"""
