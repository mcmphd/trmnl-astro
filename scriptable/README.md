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

**Not verified**: everything that only executes inside Scriptable itself —
`DrawContext` drawing calls actually producing the intended image,
`Location.current()` behavior, `ListWidget.backgroundImage` fill behavior
in a "medium"/"large" widget frame, and general on-device performance.
Expect to debug real issues the first time this actually runs in the app.

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
