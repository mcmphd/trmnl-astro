# TRMNL Astro Dashboard

A three-ring astronomical dashboard rendered as PNGs and pushed to a TRMNL
e-ink display via Webhook, on a free GitHub Actions schedule. Renders at
eight layout sizes: the four standard TRMNL sizes (Full, Half horizontal,
Half vertical, Quadrant), each with a native-portrait counterpart (width
and height swapped) for devices like XTEink that request a portrait-shaped
image directly rather than rotating the landscape one.

- **Center**: moon phase disc (illuminated fraction + waxing/waning side,
  phase name shown in the text panel — no illumination % shown, just the
  name, e.g. "Waning Crescent").
- **Middle ring**: Equation of Time polar plot — one point per day of the
  year, angle = day-of-year (Jan 1 at top, clockwise), radius = EoT minutes
  offset from a baseline circle. Today's position is marked with an open
  ring. The 12 calendar month-start days are marked with a single-letter
  abbreviation (J/F/M/A/M/J/J/A/S/O/N/D) sitting right on the loop, each
  with a small white halo so it stays legible against the loop's own black
  line. Zodiac sign glyphs are labeled separately, on the *inside* of the
  loop, at each sign's actual entry date (e.g. ♈ Aries on Mar 21) —
  deliberately distinct from the month-letter markers, which mark calendar
  months, not zodiac boundaries. Full and Full portrait (which have the
  room) show all 12 signs; the other six layouts show only whichever sign
  is currently active. Fourier method from
  [equation-of-time.info](https://equation-of-time.info/calculating-the-equation-of-time)
  (same formula previously verified in a Swift watch app). Text panel
  shows e.g. "5.6 min SLOW" (magnitude + direction word, sign dropped
  since the word already conveys it).
- **Outer ring**: 24-hour daylight/twilight/night band, **noon at top (12
  o'clock), midnight at bottom (6 o'clock)**, clockwise — night (black),
  astronomical/nautical/civil twilight (diagonal hatch at three
  densities), day (white) — with a triangular marker pointing inward at
  the ring to indicate the current time, plus a small circle sitting in
  the middle of the daylight track itself at true noon/midnight: white
  (hollow) for noon, black (filled) for midnight, each outlined in the
  opposite color so it stays visible whichever band it lands in. These
  replaced word labels ("NOON"/"MIDNIGHT") that didn't fit at smaller
  layout sizes — the circles are compact enough to show everywhere.
- **Text panel** (all layouts except Quadrant, which is graphic-only):
  date, EoT value + direction, moon phase name, and — Full and Full
  portrait only — sunrise/sunset, day length, civil twilight window. The
  other layouts drop that last block; there isn't vertical room for it at
  the same fixed font sizes Full uses (see Design decisions). Long lines
  that don't fit a layout's width wrap onto multiple lines rather than
  overflowing — needed once Half vertical portrait's 240px width turned
  out too narrow for "Waning Crescent" at a single fixed font size.

## How delivery works

TRMNL's documented Webhook strategy caps payloads at 2–5 KB of JSON
`merge_variables` — too small for an embedded image. So instead of pushing
image bytes, the Action:

1. Renders all eight `data/dashboard_<layout>.png` files and commits them
   to this repo (same pattern `trmnl-wbgt` uses for `data/latest.json` —
   free, versioned hosting via `raw.githubusercontent.com`, no separate
   image host needed).
2. POSTs one small JSON payload with eight `image_url_<layout>` fields
   (still comfortably under the cap, roughly 1.5 KB) — to the plugin's
   Webhook URL, using the *commit SHA* in each URL (not `main`) so TRMNL
   always fetches the exact new images instead of a possibly CDN-cached
   stale one.
3. Each `templates/<layout>.liquid` is just
   `<img src="{{ image_url_<layout> }}">` (the four non-portrait templates
   additionally pick between landscape/portrait via TRMNL's own
   `portrait:` variant classes — see "Portrait devices" below) — TRMNL's
   own rendering pipeline dithers it to the device's e-ink bitmap the same
   way it dithers everything else, so the images are left as antialiased
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

1. **Repo variable** (Settings → Secrets and variables → Actions → Variables):
   - `ASTRO_ZIP` — a US zip code, e.g. `23221`. The workflow resolves this
     to lat/lon (via Zippopotam.us, free/no key) and IANA timezone (via
     `timezonefinder`, computed offline from those coordinates) once per
     run, then reuses that for all eight layout renders.
2. **Repo secret**: `TRMNL_PLUGIN_UUID` — from your TRMNL Private Plugin
   (Strategy = Webhook). The UUID is the path segment in the plugin's
   webhook URL.
3. **Trigger a manual run** (Actions tab → "Render and push astro
   dashboard" → Run workflow) to test before waiting on the 6-hour cron.
4. **TRMNL plugin markup**: paste each `templates/<layout>.liquid` into
   the matching tab in the plugin's markup editor — **all four auto-select
   landscape vs. portrait** (see "Portrait devices" below), so use these
   even if your device (e.g. XTEink with TRMNL set to Portrait in its
   device settings) is portrait-oriented:
   - Full (800×480) → `templates/full.liquid`
   - Half horizontal (800×240) → `templates/half_horizontal.liquid`
   - Half vertical (400×480) → `templates/half_vertical.liquid`
   - Quadrant (400×240) → `templates/quadrant.liquid`

### Portrait devices (e.g. XTEink)

Orientation lives in TRMNL's own device settings, not the reader's
firmware — so the same plugin/template needs to serve the right image
either way, without you having to swap templates by hand if you ever flip
a device between portrait and landscape.

Each of the four templates above embeds **both** its landscape and
portrait image (e.g. `templates/full.liquid` has `image_url_full` 800×480
and `image_url_full_portrait` 480×800 — same pattern for Half
horizontal/vertical and Quadrant, each against its own portrait
counterpart, width and height swapped). Per
[TRMNL's Framework docs](https://trmnl.app/framework/docs/3.1/responsive),
**TRMNL does not use standard CSS media queries at all** — it has its own
Tailwind-style variant-class system (`sm:`/`md:`/`lg:` size breakpoints,
`1bit:`/`2bit:`/`4bit:` color-depth breakpoints, and a `portrait:`
orientation prefix, all freely combinable, e.g. `md:portrait:4bit:hidden`
from their docs). An earlier version of these templates used a plain
`@media (orientation: portrait)` CSS block, which almost certainly does
**not** work against their rendering pipeline — corrected to use their
actual `hidden`/`visible` [visibility utilities](https://trmnl.app/framework/docs/3.1/visibility)
combined with the `portrait:` prefix instead:

```html
<img class="visible portrait:hidden" src="{{ image_url_full }}" ... />
<img class="hidden portrait:visible" src="{{ image_url_full_portrait }}" ... />
```

"Landscape is the default, only `portrait:` variants are provided" per
their docs — so the landscape image is `visible` by default and hidden
in portrait, and vice versa for the portrait image.

**Please verify on your actual device** that this shows the right image
for your Portrait TRMNL setting — I validated that all four Liquid
templates parse and render both branches correctly, but couldn't render
them through TRMNL's actual framework CSS to confirm the `portrait:`
variant behaves as their docs describe. If it doesn't work, fall back to
assigning the matching `templates/<layout>_portrait.liquid` (unconditional,
no orientation detection — one exists for each of the four sizes) directly
to whatever plugin instance/playlist slot your portrait device pulls
from — the images themselves already render correctly either way, this is
purely about which template file gets the right one in front of the
device.

## Local testing

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python render_dashboard.py --zip 23221 --layout full
# or supply coordinates directly: --lat 37.5407 --lon -77.4360 --tz "America/New_York"
# --layout also accepts full_portrait / half_horizontal / half_horizontal_portrait /
# half_vertical / half_vertical_portrait / quadrant / quadrant_portrait
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
radii do.** All eight layouts assume the same e-ink DPI — a smaller layout
uses less of its panel, not a shrunk panel — so a 15pt label should stay
15pt everywhere, the same way a browser doesn't shrink your fonts when the
window gets smaller. Only the circle geometry
(`Geometry.scale = r_ring_out / 215`) scales per layout. This is also why
most non-Full layouts drop the SUN block instead of shrinking every font
to fit: shrinking would fight the same-DPI assumption, so cutting content
is the correct move once content stops fitting, not smaller type. One
corollary this created: **long text lines now word-wrap** rather than
overflow the canvas — needed once Half vertical portrait's 240px width
turned out narrower than "Waning Crescent" at fixed font size. Wrapping
adds lines rather than shrinking type, consistent with the same-DPI
principle; the extra vertical room these narrow-but-tall portrait layouts
have is exactly what makes that work instead of just overflowing worse.

**NOON/MIDNIGHT are small circle markers in the daylight track, not text
labels.** An earlier version showed the words "NOON"/"MIDNIGHT", gated to
`scale >= 0.9` (effectively Full-only) because an 8-letter word doesn't
fit the daylight annulus at smaller ring sizes with fixed (unscaled) font
size. Replaced with a white (hollow) circle for noon and a black (filled)
circle for midnight, each outlined in the opposite color for contrast
against whichever band (day/night) they land in — compact enough to work
at every layout size, so the scale gate is gone entirely.

**Noon/midnight are civil clock time, not solar time — deliberately.**
The daylight ring's "noon" mark is always 12:00 PM on the local clock
(top of the ring), computed from tz-aware Python `datetime`s, which
already shift for DST automatically (`America/New_York` reports EDT vs
EST correctly depending on date) — so no separate DST adjustment is
needed for the ring to be internally correct as a *civil* 24-hour clock
face. A different design would anchor "noon" to true *solar* noon
instead, which drifts against clock time by both DST (~1h) and the
Equation of Time itself (~±16 min) — but that would duplicate, on this
ring, exactly the divergence the EoT ring in the center already exists to
show. Kept as a civil clock face on purpose; flagged here in case a
future change wants to revisit it.
