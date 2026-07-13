# TRMNL Astro Dashboard

A three-ring astronomical dashboard rendered as PNGs and pushed to a TRMNL
e-ink display via Webhook, on a free GitHub Actions schedule. Renders at
eight layout sizes: the four standard TRMNL sizes (Full, Half horizontal,
Half vertical, Quadrant), each with a native-portrait counterpart (width
and height swapped) for devices like XTEink that request a portrait-shaped
image directly rather than rotating the landscape one.

There's also an [on-device iOS prototype](scriptable/README.md) — a
Scriptable widget port that computes and draws everything locally (no
server, no webhook), using the phone's own location and timezone. Same
astronomy math, ported to JS; see that README for status (prototype,
not yet verified on real hardware).

- **Center**: moon phase disc (illuminated fraction + waxing/waning side,
  phase name shown in the text panel — no illumination % shown, just the
  name, e.g. "Waning Crescent"). Sized 5% smaller than its first pass,
  which was large enough to overlap the ♓ Pisces glyph on the loop above it.
- **Middle ring**: Equation of Time polar plot — one point per day of the
  year, angle = day-of-year (Jan 1 at top, clockwise), radius = EoT minutes
  offset from a baseline circle. Today's position is marked with an open
  ring around a filled center dot. The 12 calendar month-start days are
  marked with a single-letter abbreviation (J/F/M/A/M/J/J/A/S/O/N/D)
  sitting right on the loop, each with a small white halo so it stays
  legible against the loop's own black line. Zodiac sign glyphs are
  labeled separately, on the *inside* of the loop — deliberately distinct
  from the month-letter markers, which mark calendar months, not zodiac
  boundaries. Full and Full portrait (which have the room) show all 12
  signs, each at its own actual entry date (e.g. ♈ Aries on Mar 21); the
  other six layouts show only whichever sign is currently active,
  positioned next to the today-marker dot rather than at its own entry
  date — showing it there instead reads as "you are here, in this sign"
  at a glance, rather than sending the eye off to a date that could be
  most of a month away from today. Fourier method from
  [equation-of-time.info](https://equation-of-time.info/calculating-the-equation-of-time)
  (same formula previously verified in a Swift watch app). Text panel
  shows e.g. "5.6 min SLOW" (magnitude + direction word, sign dropped
  since the word already conveys it).
- **Outer ring**: 24-hour daylight/twilight/night band, **noon at top (12
  o'clock), midnight at bottom (6 o'clock)**, clockwise — night (black),
  astronomical/nautical/civil twilight (diagonal hatch at three
  densities), day (white). A small circle sits in the middle of the
  daylight track itself at true noon/midnight: white (hollow) for noon,
  black (filled) for midnight, each outlined in the opposite color so it
  stays visible whichever band it lands in. (There's no live "now" marker
  — see Design decisions for why that was pulled.) These circles
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
4. **TRMNL plugin markup**: paste `templates/<layout>.liquid` into the
   matching tab in the plugin's markup editor — for a **portrait** device
   like XTEink, use `templates/<layout>_portrait.liquid` instead (see
   "Portrait devices" below for why):
   - Full (800×480) → `templates/full.liquid`, or `full_portrait.liquid`
     for a portrait device
   - Half horizontal (800×240) → `templates/half_horizontal.liquid`, or
     `half_horizontal_portrait.liquid`
   - Half vertical (400×480) → `templates/half_vertical.liquid`, or
     `half_vertical_portrait.liquid`
   - Quadrant (400×240) → `templates/quadrant.liquid`, or
     `quadrant_portrait.liquid`

### Portrait devices (e.g. XTEink)

**Confirmed on real hardware: assign the `_portrait.liquid` template
directly, don't rely on auto-detection.** `templates/full.liquid` (and
its Half/Quadrant siblings) embed both the landscape and portrait image
behind TRMNL's `portrait:` variant-class toggle:

```html
<img class="visible portrait:hidden" src="{{ image_url_full }}" ... />
<img class="hidden portrait:visible" src="{{ image_url_full_portrait }}" ... />
```

This is documented TRMNL behavior — [their Framework docs](https://trmnl.app/framework/docs/3.1/responsive)
describe `portrait:` as a real, freely-combinable variant prefix (e.g.
`md:portrait:4bit:hidden`), and it replaced an earlier, definitely-wrong
attempt using plain `@media (orientation: portrait)` CSS (TRMNL doesn't
process standard CSS at all).

Testing on real hardware narrowed down exactly where this breaks:
**the markup editor's own preview toggles portrait/landscape correctly**
(so `portrait:` is a real, working rendering feature, not a documentation
fiction) — **but the Playlist view and the physical X4 device both
ignore it**, showing the landscape image regardless of the device's
Portrait setting. That split points at the actual mechanism: the editor's
preview toggle is almost certainly a design-time-only simulation, decoupled
from how a real device's screen gets rendered. Production delivery most
likely renders each plugin size at one fixed, canonical viewport (Full is
always rendered at 800×480, say) regardless of which specific device ends
up requesting it — so `portrait:` has no live orientation signal to key off
of outside the editor. Unconfirmed (I don't have visibility into TRMNL's
render pipeline), but it fits both the docs (their other breakpoints are
tied to fixed device-model dimensions, not a dynamic per-request check) and
this editor-preview-vs-production split precisely.

Practical implication: **don't expect this to start working for other
devices, sizes, or a future TRMNL update** — treat the auto-detecting
templates as unreliable in production generally, not just misconfigured
for this one device. Whatever the exact cause, the fix is simple and now
proven: assign
`templates/<layout>_portrait.liquid` — unconditional, no orientation
detection, just always shows the portrait image — directly to whatever
plugin instance/playlist slot the portrait device pulls from. The
auto-detecting templates are left in place for anyone whose setup *does*
report as a recognized native device, but portrait BYOS devices should go
straight to the explicit `_portrait` template rather than trying the
auto-detecting one first.

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

**The "now" triangle marker on the daylight ring is off by default.** It
drew fine, but a precise hour/minute pointer is actively misleading on
this project's delivery: TRMNL renders on a 6-hour cron, so the marker
could be showing a time up to 6 hours stale — worse than showing nothing,
since it looks authoritative. `draw_daylight_ring(..., show_now_marker=...)`
and `render_dashboard.py --show-now-marker` both still exist and work
(default `False`) rather than being deleted — kept for a future delivery
path that renders closer to real time, where a live marker would
actually be accurate. The noon/midnight circles are unaffected: they mark
fixed clock positions, not "now," so staleness doesn't apply to them.

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
