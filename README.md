# TRMNL Astro Dashboard

A three-ring astronomical dashboard rendered as a single PNG and pushed to a
TRMNL e-ink display via Webhook, on a free GitHub Actions schedule.

- **Center**: moon phase disc (illuminated fraction + waxing/waning side).
- **Middle ring**: Equation of Time polar plot — one point per day of the
  year, angle = day-of-year (Jan 1 at top, clockwise), radius = EoT minutes
  offset from a baseline circle. Today's position is marked with an open
  ring. Fourier method from
  [equation-of-time.info](https://equation-of-time.info/calculating-the-equation-of-time)
  (same formula previously verified in a Swift watch app).
- **Outer ring**: 24-hour daylight/twilight/night band (midnight at top,
  clockwise) — night (black), astronomical/nautical/civil twilight
  (graduated grays), day (white) — with a marker for the current time.
- **Text panel**: date, EoT value (minutes, fast/slow), moon phase name and
  illumination %, sunrise/sunset, day length, civil twilight window.

## How delivery works

TRMNL's documented Webhook strategy caps payloads at 2–5 KB of JSON
`merge_variables` — too small for an embedded image. So instead of pushing
image bytes, the Action:

1. Renders `data/dashboard.png` and commits it to this repo (same pattern
   `trmnl-wbgt` uses for `data/latest.json` — free, versioned hosting via
   `raw.githubusercontent.com`, no separate image host needed).
2. POSTs a small JSON payload — just `{"merge_variables": {"image_url": "..."}}`
   — to the plugin's Webhook URL, using the *commit SHA* in the URL
   (not `main`) so TRMNL always fetches the exact new image instead of a
   possibly CDN-cached stale one.
3. `templates/astro.liquid` is just `<img src="{{ image_url }}">` — TRMNL's
   own rendering pipeline dithers it to the device's e-ink bitmap the same
   way it dithers everything else, so the image is left as antialiased
   8-bit grayscale rather than pre-dithered.

**Verify the webhook domain before relying on this.** The docs I could
fetch state the endpoint as `https://trmnl.com/api/custom_plugins/{UUID}`,
but TRMNL's docs site recently migrated off `usetrmnl.com` and I could not
confirm live whether the *API* domain (as opposed to the docs site) has
also moved. Open your Private Plugin's settings page in the TRMNL
dashboard — it displays the exact Webhook URL to POST to. If it says
`usetrmnl.com` instead of `trmnl.com`, fix the domain in
`.github/workflows/astro.yml` before enabling the schedule.

## Setup

1. **Repo variables** (Settings → Secrets and variables → Actions → Variables):
   - `ASTRO_LAT`, `ASTRO_LON` — your coordinates.
   - `ASTRO_TZ` — IANA timezone name, e.g. `America/New_York`.
2. **Repo secret**: `TRMNL_PLUGIN_UUID` — from your TRMNL Private Plugin
   (Strategy = Webhook). The UUID is the path segment in the plugin's
   webhook URL.
3. **Trigger a manual run** (Actions tab → "Render and push astro
   dashboard" → Run workflow) to test before waiting on the 3-hour cron.
4. **TRMNL plugin markup**: paste `templates/astro.liquid` into the
   plugin's markup editor (Full layout, 800×480, matches the rendered
   image's aspect ratio).

## Local testing

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python render_dashboard.py --lat 37.5407 --lon -77.4360 --tz "America/New_York" --out data/dashboard.png
```

Text rendering needs a TTF font. The script looks for
`/usr/share/fonts/truetype/dejavu/DejaVuSans*.ttf` (installed via
`apt-get install fonts-dejavu-core` in CI) and falls back to
`FONT_REGULAR`/`FONT_BOLD` env vars, then to PIL's tiny built-in bitmap
font if neither is found — set the env vars if testing on a machine
without DejaVu installed.

## Design decisions

**Fixed calendar orientation, not a rolling window.** The EoT loop spans
Jan 1–Dec 31 of the current year with Jan 1 always at the top, so the
loop's shape and the month tick marks are stable day to day — only the
"today" marker moves. An earlier version centered a rolling 365-day
window on "today" instead; that made the *whole loop* rotate through the
year, which reads as noise rather than a fixed reference frame.

**Moon phase math uses astral's 28-day normalized scale**, not the true
29.53-day synodic month — fine for a decorative illumination-fraction
render, not for precision timekeeping.

**Twilight bands are flat gray steps, not hatch patterns.** A hatch-pattern
treatment (matching the engraved-dial aesthetic this project started from)
was considered but dropped for time; flat grays dither cleanly and are
easy to verify programmatically. Worth revisiting if the rendered device
output looks muddy.
