# Mobile-Layout-Regression-Sweep

`mobile_layout_sweep.py` klickt im iPhone-Viewport (390×844) durch alle
Hauptseiten der MeetFlow-App und prüft, ob `fixed`/`absolute` positionierte
Elemente (Floating Menus wie Avatar oder NotificationBell oben rechts) mit
Content-Buttons überlappen. So fangen wir Mobile-Layout-Konflikte wie den
in Iter 379 entdeckten Chat-`+`/UserMenu-Konflikt **vor** der Production-
Deployment ab.

## Voraussetzungen

```bash
playwright install chromium    # nur beim ersten Mal noetig
```

## Verwendung

```bash
# Default: Preview-URL mit qa_member-Account
python3 /app/scripts/mobile_layout_sweep.py

# Andere URL / anderer Account
python3 /app/scripts/mobile_layout_sweep.py \
  --url https://video-meet-pro.preview.emergentagent.com \
  --email qa_admin@meetflow.com \
  --password qa_admin_pw_372

# JSON-Report (fuer CI)
python3 /app/scripts/mobile_layout_sweep.py --json
```

## Exit-Codes

- `0` — alle Seiten sauber, keine Overlaps
- `1` — mindestens ein Overlap gefunden (Details im Stdout)

## Geprüfte Seiten (Stand Iter 379)

- `/dashboard`
- `/chat`
- `/meetings`
- `/tasks`
- `/news`
- `/calendar`

Weitere Seiten lassen sich einfach in der `PAGES`-Liste in
`mobile_layout_sweep.py` ergaenzen.

## Erweitern

Floating-Selektoren werden in `FLOATING_SELECTORS` definiert. Jeder neue
Selektor wird automatisch gegen alle Content-Buttons mit `data-testid`
auf jeder Seite geprueft. Falls neue Floating-Elemente hinzukommen
(z. B. ein neuer Help-FAB unten rechts), einfach den `data-testid` dort
eintragen.
