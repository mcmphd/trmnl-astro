# Astro Widget (Scriptable prototype)

An on-device iOS port of the TRMNL astro dashboard (moon phase / Equation
of Time loop / daylight ring), built for [Scriptable](https://scriptable.app).
No server, no GitHub Action, no webhook — the phone computes and draws
everything itself on each widget refresh, using its own location and
timezone directly (no zip-code geocoding step, unlike the TRMNL version).

## Status: prototype, unverified on real hardware

I have no way to execute Scriptable's `DrawContext`/`Location`/`ListWidget`
APIs from this environment — they're iOS-only. What's actually verified,
and how:

- **`astro-core.js`'s astronomy math** (Equation of Time, solar
  declination, sunrise/sunset/twilight, moon phase, zodiac sign) — run and
  checked against the Python/`astral` reference values via plain Node (no
  Scriptable APIs involved). Agrees to within 1-2 minutes on sunrise/sunset
  and matches exactly on moon phase name and zodiac sign for the test
  dates checked. A **real bug was caught and fixed this way**: an inverted
  depression-angle sign gave sunrise/sunset times off by 8-9 minutes each
  side until corrected (see git history).
- **The moon crescent geometry** (`moonLitPath`'s waxing/waning logic in
  `astro-widget.js`) — re-implemented outside Scriptable in a standalone
  Node script (point-in-polygon test over a sampled grid) to confirm which
  half of the disc ends up lit and by how much, for 6 test cases (15%/
  50%/85% illumination × waxing/waning). Matches the same left/right
  pattern already validated for the Python version.
- **Two more real bugs were caught by careful re-reading**, without being
  able to run the code: a malformed ternary that silently zeroed the
  timezone offset in all cases, and "today"/day-boundary calculations that
  read UTC calendar fields directly off an unshifted instant (would
  misidentify "today," and the whole daylight ring's angles, for several
  hours every evening in US timezones — worse the further behind UTC).
  Both fixed; see the `localCalendarDay()` comment for the reasoning.

**Confirmed working on real hardware** as of the first on-device test: the
widget renders and shows on a Home Screen. One real bug surfaced on that
first run — `respectScreenScale` has to be the very first thing set after
`new DrawContext()`, before any other property or drawing call, or
Scriptable throws at runtime. Fixed.

**Still not verified**: `ListWidget.backgroundImage` fill behavior in a
"medium"/"large" widget frame (only "small" is composed for so far), and
general on-device performance over repeated refreshes.

## Color, emoji, and background

Unlike the monochrome e-ink TRMNL version, this renders in full color:

- **Daylight ring**: sky blue (day), three teal shades graduating toward
  night (civil → nautical → astronomical twilight), Payne's grey (night).
  These replace the TRMNL version's diagonal-hatch twilight bands — that
  hatching only existed to survive 1-bit e-ink dithering, so plain color
  fills replace it directly, no workaround needed.
- **Noon/midnight markers**: 🌞/🌛 ("sun with face" / "first quarter moon
  with face") instead of the TRMNL version's white/black circles.
- **Month letters**: sized up (7pt → 9.5pt at reference scale) for
  legibility.
- **Ring size**: the whole composition is ~12% smaller within the same
  canvas (`RING_SHRINK` near the top of `astro-widget.js`), leaving more
  margin around it.

Exact hex values (`SKY_BLUE`, `TWILIGHT_TEAL_*`, `PAYNES_GREY`) are my best
approximation of the named colors requested — nudge them directly if they
don't match what you had in mind; I have no way to preview actual color
rendering from this environment.

**`drawTextInRect` does not center text**, contrary to what its name
suggests — confirmed from an on-device screenshot showing both the sun/moon
emoji AND the plain month-letters shifted up and to the left of their
intended position, so it isn't an emoji-glyph-metrics quirk, it's
`drawTextInRect` itself (apparently left/top-aligning). `drawCenteredText()`
applies an empirical compensation (`TEXT_NUDGE_FRAC`, currently 0.45) shared
by every text-on-the-graphic call site — one place to retune if a
particular glyph still isn't quite centered.

**Known remaining issue, not yet addressed**: the zodiac glyph showed as a
small tofu/placeholder box in the one on-device screenshot seen so far,
rather than the intended character. The README previously noted this was
*unverified* whether iOS's system font covers the astrological Unicode
block (U+2648-2653) — that screenshot suggests it may not, at least not at
the font/size used. Not fixed yet since it wasn't reported as something to
fix this round; likely needs either a different system font name or a
larger point size to resolve.

### Background: true transparency isn't possible on iOS Home Screen widgets

First attempt used a fully transparent rendered image (`ctx.opaque =
false`, no fill) hoping iOS would show the wallpaper through it. Confirmed
on real hardware that this doesn't work: **iOS forces its own opaque/light
backing behind every Home Screen widget regardless of what alpha you
draw**, which is why the widget still showed stark white. This isn't a bug
in this script — it's a platform limitation. The community's "invisible
widget" workaround fakes it by screenshotting the actual wallpaper,
cropping to the widget's exact position and size, and using that
screenshot as the background image (see e.g. the [Automators Talk
thread on invisible Scriptable widgets](https://talk.automators.fm/t/invisible-widget-generator/9235)) —
essentially camouflage, not real transparency, and it breaks if you change
wallpaper or the widget's position. **Not implemented here** given that
fragility; open to adding it if you want the full effect.

What's here instead: `widget.backgroundColor` is set explicitly to a pale,
cool-toned color to override iOS's forced white with something closer to a
frosted-glass look, while the rendered image itself stays transparent so
the ring's circular shape floats on that color rather than sitting in a
hard-edged square card. It's also **day/night aware**: `renderImage()`
returns `isDaytime` (now between sunrise and sunset) alongside the image,
and `main()` picks a slightly darker shade for daytime (`#D7DEE3`) than
night (`#EEF1F4`) — the paler night shade read fine against the dark
Payne's grey band, but felt washed out against the bright sky-blue day
band.

## Setup

1. Install [Scriptable](https://apps.apple.com/app/scriptable/id1405459188)
   (free) if you don't have it.
2. Create two new scripts in the app, named exactly:
   - `astro-core` — paste in `astro-core.js`'s contents
   - `astro-widget` — paste in `astro-widget.js`'s contents

   (Scriptable's `importModule("astro-core")` resolves by script name, not
   filename with extension — the `.js` here is just this repo's convention
   for editor syntax highlighting.)
3. Run `astro-widget` once directly in the app (tap the script, not as a
   widget yet) to grant Location permission when prompted, and to confirm
   it produces a Quick Look image without errors.
4. Add a Scriptable widget to your Home Screen (long-press Home Screen →
   `+` → Scriptable → small size), then long-press it → Edit Widget →
   set Script to `astro-widget`.

If you'd rather not grant Location access, edit `FALLBACK_LAT`/
`FALLBACK_LON` at the top of `astro-widget.js` to your coordinates —
the script falls back to those automatically if Location is denied or
unavailable, but still asks for permission on first run.

## Known gaps in this first pass

- **Only the small (square) widget size is actually composed for.**
  Medium/large will get the same square image as their background,
  which iOS will very likely center-crop into the wider frame (clipping
  the sides of the daylight ring) rather than distort — but this is
  genuinely unverified. A text-panel layout for medium/large (mirroring
  the Python "full" layout's graphic+text side-by-side composition) is a
  reasonable next step once the small case is confirmed working.
- **No live "now" marker on the daylight ring**, matching the TRMNL
  version's current state — but for a different reason. The TRMNL version
  removed it because a 6-hour render cadence makes a precise time marker
  actively misleading. This script recomputes on every widget refresh, so
  a "now" marker *would* be accurate here — it's just left out of this
  pass to keep the port a faithful match to the current Python design.
  Straightforward to add back (see the removed code in `render_dashboard.py`'s
  git history for the exact triangle-marker geometry) if you want it.
- **Moon phase uses a true 29.53-day synodic-month calculation**, not
  Python `astral`'s 28-day normalized scale — expect illumination % to
  differ from the TRMNL images by up to a few percentage points on any
  given day. Neither is precision timekeeping; both are decorative,
  consistent with the caveat already documented for the Python version.
- **Zodiac glyphs use the plain iOS system font**, not a dedicated symbol
  font — Apple's system font covers the astrological Unicode block
  (U+2648-2653) in my experience, but this hasn't been confirmed on this
  specific Scriptable/iOS version combination the way the Python version's
  DejaVu Sans requirement was confirmed by actually rendering all 12
  glyphs.

## Files

- `astro-core.js` — pure-JS astronomy math, no Scriptable dependency.
  Runs fine under plain Node for testing (`node -e "require('./astro-core.js')..."`).
- `astro-widget.js` — Scriptable-specific: `DrawContext` rendering,
  `Location`/`Intl` for on-device position and timezone, widget wiring.
  Cannot run outside Scriptable (uses `Path`, `DrawContext`, `Color`,
  `Font`, `ListWidget`, `Location`, `QuickLook`, `config`, `Script` — all
  Scriptable globals).
