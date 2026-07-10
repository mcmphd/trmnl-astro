# TRMNL Astro Dashboard

A three-ring astronomical dashboard rendered as PNGs and pushed to a TRMNL
e-ink display via Webhook, on a free GitHub Actions schedule. Renders at
five layout sizes: the four standard TRMNL sizes (Full, Half horizontal,
Half vertical, Quadrant) plus a native-portrait Full variant (480×800) for
devices like XTEink that request a portrait-shaped image directly rather
than rotating the landscape one.

- **Center**: moon phase disc (illuminated fraction + waxing/waning side,
  phase name shown in the text panel — no illumination % shown, just the
  name, e.g. "Waning Crescent").
- **Middle ring**: Equation of Time polar plot — one point per day of the
  year, angle = day-of-year (Jan 1 at top, clockwise), radius = EoT minutes
  offset from a baseline circle. Today's position is marked with an open
  ring; the 12 month-start days are marked with dots, and the four cardinal
  months (Jan/Apr/Jul/Oct) are additionally labeled with their zodiac sign
  (♑/♈/♋/♎ — the tropical sign in effect on the 1st of that month). Fourier
  method from
  [equation-of-time.info](https://equation-of-time.info/calculating-the-equation-of-time)
  (same formula previously verified in a Swift watch app). Text panel
  shows e.g. "5.6 min SLOW" (magnitude + direction word, sign dropped
  since the word already conveys it).
- **Outer ring**: 24-hour daylight/twilight/night band, **noon at top (12
  o'clock), midnight at bottom (6 o'clock)**, clockwise — night (black),
  astronomical/nautical/civil twilight (diagonal hatch at three
  densities), day (white) — with a triangular marker pointing inward at
  the ring to indicate the current time. The NOON/MIDNIGHT text labels
  only render in the Full and Full portrait layouts — at smaller sizes
  there isn't room for an 8-letter word next to a zodiac glyph at fixed
  font size, so only the long tick marks at true 0°/180° remain.
- **Text panel** (all layouts except Quadrant, which is graphic-only):
  date, EoT value + direction, moon phase name, and — Full and Full
  portrait only — sunrise/sunset, day length, civil twilight window. Half
  horizontal and Half vertical drop that last block; there isn't vertical
  room for it at the same fixed font sizes Full uses (see Design
  decisions).

## How delivery works

TRMNL's documented Webhook strategy caps payloads at 2–5 KB of JSON
`merge_variables` — too small for an embedded image. So instead of pushing
image bytes, the Action:

1. Renders all five `data/dashboard_<layout>.png` files and commits them
   to this repo (same pattern `trmnl-wbgt` uses for `data/latest.json` —
   free, versioned hosting via `raw.githubusercontent.com`, no separate
   image host needed).
2. POSTs one small JSON payload with five `image_url_<layout>` fields —
   to the plugin's Webhook URL, using the *commit SHA* in each URL (not
   `main`) so TRMNL always fetches the exact new images instead of a
   possibly CDN-cached stale one.
3. Each `templates/<layout>.liquid` is just
   `<img src="{{ image_url_<layout> }}">` — TRMNL's own rendering pipeline
   dithers it to the device's e-ink bitmap the same way it dithers
   everything else, so the images are left as antialiased 8-bit grayscale
   rather than pre-dithered.

**Verify the webhook domain before relying on this.** The docs I could
fetch state the endpoint as `https://trmnl.com/api/custom_plugins/{UUID}`,
but TRMNL's docs site recently migrated off `usetrmnl.com` and I could not
confirm live whether the *API* domain (as opposed to the docs site) has
also moved. Open your Private Plugin's settings page in the TRMNL
dashboard — it displays the exact Webhook URL to POST to. If it says
`usetrmnl.com` instead of `trmnl.com`, fix the domain in
`.github/workflows/astro.yml` before enabling the schedule.

## Setup

1. **Repo variable** (Settings → Secrets and variables → Actions → Variables):
   - `ASTRO_ZIP` — a US zip code, e.g. `23221`. The workflow resolves this
     to lat/lon (via Zippopotam.us, free/no key) and IANA timezone (via
     `timezonefinder`, computed offline from those coordinates) once per
     run, then reuses that for all five layout renders.
2. **Repo secret**: `TRMNL_PLUGIN_UUID` — from your TRMNL Private Plugin
   (Strategy = Webhook). The UUID is the path segment in the plugin's
   webhook URL.
3. **Trigger a manual run** (Actions tab → "Render and push astro
   dashboard" → Run workflow) to test before waiting on the 6-hour cron.
4. **TRMNL plugin markup**: paste each `templates/<layout>.liquid` into
   the matching tab in the plugin's markup editor:
   - Full (800×480) → `templates/full.liquid`
   - Full portrait (480×800) → `templates/full_portrait.liquid` — for
     devices that request a native portrait image (e.g. XTEink), rather
     than rotating the landscape Full image themselves
   - Half horizontal (800×240) → `templates/half_horizontal.liquid`
   - Half vertical (400×480) → `templates/half_vertical.liquid`
   - Quadrant (400×240) → `templates/quadrant.liquid`

## Local testing

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python render_dashboard.py --zip 23221 --layout full
# or supply coordinates directly: --lat 37.5407 --lon -77.4360 --tz "America/New_York"
# --layout also accepts half_horizontal / half_vertical / quadrant
# (defaults to writing data/dashboard_<layout>.png if --out isn't given)
```

Body text renders in **DejaVu Serif** (`FONT_REGULAR`/`FONT_BOLD`, falling
back to `/usr/share/fonts/truetype/dejavu/DejaVuSerif*.ttf` in CI). The
zodiac glyphs (U+2648–U+2653) on the EoT loop are a **separate font**
(`FONT_SYMBOL`, falling back to `DejaVuSans.ttf`) — confirmed by actually
rendering all 12 glyphs that DejaVu Serif doesn't include the astrological
symbol block at all (tofu boxes), while DejaVu Sans does. `fonts-dejavu-core`
(installed via `apt-get` in CI) ships both families, so this needs no extra
package. On a machine without DejaVu installed, point all three env vars
at TTFs that cover what's needed — e.g. the copies bundled inside an
installed `matplotlib` package
(`matplotlib/mpl-data/fonts/ttf/DejaVuSerif.ttf` /
`DejaVuSerif-Bold.ttf` / `DejaVuSans.ttf`) work fine for local testing
without a system font install. If none of the three are found, everything
falls back to PIL's tiny built-in bitmap font (no zodiac glyph support).

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

**Twilight bands are diagonal hatch patterns, not flat grays.** An earlier
version used flat gray fills (64/128/192) for astronomical/nautical/civil
twilight. Simulating TRMNL's two plausible rendering paths locally —
`Image.convert("1")` (Floyd-Steinberg dither) vs. a naive `> 127` threshold
— showed the flat grays survived dithering but **collapsed to solid
black/white and erased the twilight structure entirely under simple
thresholding**. Since which path TRMNL's pipeline actually uses for an
embedded `<img>` couldn't be confirmed without live device access, the
bands were switched to diagonal hatching at three densities (already pure
black/white, so both paths render them identically) — same fix that made
the moon crescent robust, applied to the twilight ring. Known remaining
limitation: each twilight stage is only ~8–10° of arc, so the three
densities are hard to tell apart by eye at this ring size even though they
survive processing correctly — an inherent tension between ring
compactness and stage count, not a rendering bug.

**Font sizes and stroke widths don't scale down with the layout; ring
radii do.** All five layouts assume the same e-ink DPI — a smaller layout
uses less of its panel, not a shrunk panel — so a 15pt label should stay
15pt everywhere, the same way a browser doesn't shrink your fonts when the
window gets smaller. Only the circle geometry
(`Geometry.scale = r_ring_out / 215`) scales per layout. This is also why
Half horizontal/vertical drop the SUN block instead of shrinking every
font to fit: shrinking would fight the same-DPI
assumption, so cutting content is the correct move once content stops
fitting, not smaller type.

**NOON/MIDNIGHT text labels are gated to `scale >= 0.9`** (effectively
Full only). They're nudged 25°/205° off the exact 0°/180° axis so they
don't sit radially under the Jan/Jul zodiac glyphs, which are also
anchored near 0°/180° — but at smaller ring sizes, an 8-letter word next
to a zodiac glyph collides regardless of the nudge, since font size is
fixed absolute while the ring's radial gap keeps shrinking. Rather than
keep tuning nudge angles per layout, smaller layouts just drop the words;
the long tick marks at true 0°/180° still mark noon/midnight.
