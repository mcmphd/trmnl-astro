// Astro Widget -- on-device iOS Scriptable port of the TRMNL astro
// dashboard (moon phase / Equation of Time loop / daylight ring).
//
// PARTIALLY VERIFIED ON DEVICE: I have no way to execute Scriptable's
// DrawContext API from this environment (it's iOS-only), so this was
// built by careful reading against Scriptable's documented API, not by
// running it, then fixed against real on-device errors as they came in.
// First on-device run hit one: `respectScreenScale` has to be set
// immediately after `new DrawContext()`, before any other property or
// drawing call, or Scriptable throws -- fixed. astro-core.js's math is
// separately validated against the Python/astral reference values via
// Node (see scriptable/README.md). Expect more real issues to surface as
// testing continues -- this is still an early prototype.
//
// Needs astro-core.js saved alongside this script in the same Scriptable
// folder (Scriptable > this script's folder), referenced by importModule.
//
// No zip/geocoding step, unlike the TRMNL version -- the phone already
// knows its own location and timezone.

const AstroCore = importModule("astro-core");

// ---- configuration -----------------------------------------------------

// Fallback location if Location access is denied or unavailable (e.g.
// testing in the in-app editor without granting permission). Edit to
// your own coordinates.
const FALLBACK_LAT = 37.5583;
const FALLBACK_LON = -77.4845;

const BLACK = Color.black();
const WHITE = Color.white();

// Color palette (iOS only has real color, unlike the e-ink TRMNL version --
// this also means the hatch-pattern twilight bands aren't needed here; they
// existed purely to survive 1-bit dithering, so plain color fills replace
// them below). Hex values are my best approximation of the named colors
// requested; nudge these directly if they don't match what you had in mind.
const SKY_BLUE = new Color("#87CEEB");
const TWILIGHT_TEAL_NEAR_DAY = new Color("#8FBFBA");
const TWILIGHT_TEAL_MID = new Color("#5E9C97");
const TWILIGHT_TEAL_NEAR_NIGHT = new Color("#3A6E6A");
const PAYNES_GREY = new Color("#536878");
const SUN_EMOJI = "🌞"; // "sun with face" -- smiling sun
const MOON_EMOJI = "🌛"; // "first quarter moon with face" -- smiling crescent profile

// ---- geometry (mirrors render_dashboard.py's Geometry class) -----------

// Reference ring radii (points, at a canvas of REF_SIZE x REF_SIZE) that
// every actual render size scales from -- same "radii scale, fonts and
// stroke widths don't" principle as the Python version, adapted for a much
// smaller on-device canvas than TRMNL's 800x480.
const REF_SIZE = 300;
// Shrinks the whole composition within the same REF_SIZE canvas, leaving
// more margin around the ring -- tune this one number rather than each
// radius individually.
const RING_SHRINK = 0.88;
const REF_R_RING_OUT = 140 * RING_SHRINK;
const REF_R_RING_IN = 120 * RING_SHRINK;
const REF_R_EOT_BASE = 78 * RING_SHRINK;
const REF_R_EOT_AMP = 1.8 * RING_SHRINK; // points per EoT-minute
const REF_R_MOON = 34 * 0.95 * RING_SHRINK; // 0.95 = 5% smaller, same fix as the Python version (Pisces clearance)

function makeGeometry(canvasSize) {
  const scale = canvasSize / REF_SIZE;
  return {
    scale,
    cx: canvasSize / 2,
    cy: canvasSize / 2,
    rRingOut: REF_R_RING_OUT * scale,
    rRingIn: REF_R_RING_IN * scale,
    rEotBase: REF_R_EOT_BASE * scale,
    rEotAmp: REF_R_EOT_AMP * scale,
    rMoon: REF_R_MOON * scale,
  };
}

function polarPoint(cx, cy, r, angleDeg) {
  // angleDeg measured clockwise from straight up (12 o'clock), matching
  // the Python version's convention.
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return new Point(cx + r * Math.cos(rad), cy + r * Math.sin(rad));
}

function hourAngleDeg(date, tzOffsetMinutes) {
  // Degrees clockwise from top (=noon local time), midnight at bottom --
  // same convention as render_dashboard.py's hour_angle_deg. tzOffsetMinutes
  // is the LOCAL offset from UTC in minutes (e.g. -240 for EDT).
  const localMs = date.getTime() + tzOffsetMinutes * 60000;
  const localDate = new Date(localMs);
  const secs =
    localDate.getUTCHours() * 3600 + localDate.getUTCMinutes() * 60 + localDate.getUTCSeconds();
  const secsFromNoon = (((secs - 12 * 3600) % 86400) + 86400) % 86400;
  return (secsFromNoon / 86400) * 360;
}

function dayAngleDeg(fracOfYear) {
  return fracOfYear * 360;
}

// Given a true UTC instant and a local tz offset (minutes, UTC-to-local),
// returns two things derived from the SAME local calendar day:
//  - `today`: a plain Date.UTC(Y,M,D) container carrying just the local
//    calendar date, no instant meaning -- matches how eotCalendarYear's
//    dates and AstroCore's date-only functions (sunTimes, moonIllumination,
//    currentZodiacGlyph) already treat dates: fields read via getUTC*(),
//    never compared as instants.
//  - `dayStart`: the TRUE UTC instant of local midnight on that same day
//    -- needed anywhere a value flows through hourAngleDeg(), which
//    applies its own +tzOffsetMinutes shift and would double-shift a
//    "today" value if given one instead.
function localCalendarDay(trueNowUTC, tzOffsetMinutes) {
  const shifted = new Date(trueNowUTC.getTime() + tzOffsetMinutes * 60000);
  const localYMD = Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), shifted.getUTCDate());
  const today = new Date(localYMD);
  const dayStart = new Date(localYMD - tzOffsetMinutes * 60000);
  return { today, dayStart };
}

// ---- drawing -------------------------------------------------------------

// Builds a closed Path approximating an annulus wedge (pie-slice ring
// segment) between two radii and two angles, by sampling points along
// each arc -- Scriptable's Path has no native pie-slice primitive, so
// this is the same "sample the curve into line segments" technique
// already used for the EoT loop itself.
function wedgePath(cx, cy, rOuter, rInner, a0, a1, stepDeg) {
  const path = new Path();
  const steps = Math.max(2, Math.ceil(Math.abs(a1 - a0) / stepDeg));
  let started = false;
  for (let i = 0; i <= steps; i++) {
    const a = a0 + ((a1 - a0) * i) / steps;
    const p = polarPoint(cx, cy, rOuter, a);
    if (!started) {
      path.move(p);
      started = true;
    } else {
      path.addLine(p);
    }
  }
  for (let i = steps; i >= 0; i--) {
    const a = a0 + ((a1 - a0) * i) / steps;
    path.addLine(polarPoint(cx, cy, rInner, a));
  }
  path.closeSubpath();
  return path;
}

function drawDaylightRing(ctx, geo, dayStart, tzOffsetMinutes, times) {
  // `dayStart` must be the TRUE UTC instant of local midnight (see
  // localCalendarDay() above) -- NOT today's date with UTC hours zeroed,
  // which would be off by tzOffsetMinutes and silently
  // double-shift everything passed through hourAngleDeg() below (that
  // function applies its own +tzOffsetMinutes shift, expecting a true
  // instant as input, the same way times.sunrise/etc. already are).
  const { cx, cy, rRingOut: rOut, rRingIn: rIn, scale } = geo;
  const dayEnd = new Date(dayStart.getTime() + 86400000);

  const a = (d) => hourAngleDeg(d, tzOffsetMinutes);

  // (start, end, fill) -- solid color throughout, no hatch patterns. Those
  // existed only so the twilight bands would survive 1-bit e-ink dithering
  // on the TRMNL version; real color makes that unnecessary.
  const bands = [
    [dayStart, times.dawnAstronomical, PAYNES_GREY],
    [times.dawnAstronomical, times.dawnNautical, TWILIGHT_TEAL_NEAR_NIGHT],
    [times.dawnNautical, times.dawnCivil, TWILIGHT_TEAL_MID],
    [times.dawnCivil, times.sunrise, TWILIGHT_TEAL_NEAR_DAY],
    [times.sunrise, times.sunset, SKY_BLUE],
    [times.sunset, times.duskCivil, TWILIGHT_TEAL_NEAR_DAY],
    [times.duskCivil, times.duskNautical, TWILIGHT_TEAL_MID],
    [times.duskNautical, times.duskAstronomical, TWILIGHT_TEAL_NEAR_NIGHT],
    [times.duskAstronomical, dayEnd, PAYNES_GREY],
  ];

  for (const [start, end, fill] of bands) {
    if (!start || !end) continue; // polar day/night: an event never occurred
    let a0 = a(start);
    let a1 = a(end);
    if (a1 <= a0) a1 += 360;
    const path = wedgePath(cx, cy, rOut, rIn, a0, a1, 2);
    ctx.addPath(path);
    ctx.setFillColor(fill);
    ctx.fillPath();
  }

  // crisp edge circles
  ctx.setStrokeColor(BLACK);
  ctx.setLineWidth(1.5);
  ctx.strokeEllipse(new Rect(cx - rOut, cy - rOut, rOut * 2, rOut * 2));
  ctx.strokeEllipse(new Rect(cx - rIn, cy - rIn, rIn * 2, rIn * 2));

  // hour ticks, every 3h, longer at 0/6/12/18. Each tick is `dayStart`
  // (true instant of local midnight) plus h true hours -- NOT
  // setUTCHours(h), which would set the UTC hour field directly rather
  // than stepping through *local* hours 0-23.
  for (let h = 0; h < 24; h++) {
    const tickDate = new Date(dayStart.getTime() + h * 3600000);
    const ang = a(tickDate);
    const longTick = h % 6 === 0;
    const r0 = rIn - (longTick ? 9 : 4) * scale;
    ctx.setStrokeColor(BLACK);
    ctx.setLineWidth(1);
    const path = new Path();
    path.move(polarPoint(cx, cy, r0, ang));
    path.addLine(polarPoint(cx, cy, rIn, ang));
    ctx.addPath(path);
    ctx.strokePath();
  }

  // noon / midnight markers: sun/moon emoji sitting in the track itself,
  // replacing the white/black circles from the TRMNL (monochrome) version
  // now that real color and emoji are available. No live "now" marker --
  // same reasoning as the TRMNL version: misleading once there's any gap
  // between renders. On-device this script recomputes live on every
  // widget refresh, so unlike the TRMNL version a "now" marker WOULD be
  // accurate here -- left out of this first pass to keep the port a
  // faithful match; add one back in if you want it.
  const rMid = (rIn + rOut) / 2;
  const emojiFont = Font.systemFont(11 * scale);
  ctx.setFont(emojiFont);
  // Empirical vertical nudge, tuned from an on-device screenshot: both
  // emoji rendered noticeably above the intended center of their bounding
  // box (the sun sat high/outside the day band, the moon sat high/inside
  // toward the loop) -- drawTextInRect apparently doesn't vertically
  // center emoji glyphs the way it would plain text, or color-emoji font
  // metrics carry extra headroom. Shifting the box down compensates;
  // may need further tuning.
  const yNudge = 0.35;
  for (const [ang, emoji] of [
    [0, SUN_EMOJI],
    [180, MOON_EMOJI],
  ]) {
    const p = polarPoint(cx, cy, rMid, ang);
    const w = 11 * scale;
    ctx.drawTextInRect(emoji, new Rect(p.x - w, p.y - w + yNudge * w, w * 2, w * 2));
  }
}

const MONTH_INITIAL = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

function drawEotLoop(ctx, geo, today, yearPoints, zodiacAll) {
  const { cx, cy, scale } = geo;
  const eotRadius = (eotMin) => geo.rEotBase + eotMin * geo.rEotAmp;
  const yearLen = yearPoints.length;
  const angleForIndex = (i) => dayAngleDeg(i / yearLen);

  // 0-min reference circle + +-10min guide circles
  ctx.setStrokeColor(new Color("#000000", 0.35));
  ctx.setLineWidth(0.5);
  const rBase = geo.rEotBase;
  ctx.strokeEllipse(new Rect(cx - rBase, cy - rBase, rBase * 2, rBase * 2));
  ctx.setStrokeColor(new Color("#000000", 0.22));
  for (const guide of [-10, 10]) {
    const r = eotRadius(guide);
    ctx.strokeEllipse(new Rect(cx - r, cy - r, r * 2, r * 2));
  }

  // the loop itself
  const path = new Path();
  let todayIdx = 0;
  yearPoints.forEach((pt, i) => {
    const ang = angleForIndex(i);
    const r = eotRadius(pt.eotMinutes);
    const p = polarPoint(cx, cy, r, ang);
    if (i === 0) path.move(p);
    else path.addLine(p);
    if (
      pt.date.getUTCFullYear() === today.getUTCFullYear() &&
      pt.date.getUTCMonth() === today.getUTCMonth() &&
      pt.date.getUTCDate() === today.getUTCDate()
    ) {
      todayIdx = i;
    }
  });
  path.closeSubpath();
  ctx.addPath(path);
  ctx.setStrokeColor(BLACK);
  ctx.setLineWidth(1.6 * scale);
  ctx.strokePath();

  // month-start letters, right on the loop, with a white halo so they
  // read against the loop's own line
  const monthFont = Font.boldSystemFont(9.5 * scale);
  ctx.setFont(monthFont);
  yearPoints.forEach((pt, i) => {
    if (pt.date.getUTCDate() !== 1) return;
    const ang = angleForIndex(i);
    const r = eotRadius(pt.eotMinutes);
    const p = polarPoint(cx, cy, r, ang);
    const letter = MONTH_INITIAL[pt.date.getUTCMonth()];
    const haloR = 6.5 * scale;
    ctx.setFillColor(WHITE);
    ctx.fillEllipse(new Rect(p.x - haloR, p.y - haloR, haloR * 2, haloR * 2));
    ctx.setTextColor(BLACK);
    ctx.drawTextInRect(letter, new Rect(p.x - haloR, p.y - haloR * 0.8, haloR * 2, haloR * 1.6));
  });

  // today marker: open ring around a filled center dot
  const ang0 = angleForIndex(todayIdx);
  const r0 = eotRadius(yearPoints[todayIdx].eotMinutes);
  const p0 = polarPoint(cx, cy, r0, ang0);
  const rr = Math.max(3, 5 * scale);
  ctx.setStrokeColor(BLACK);
  ctx.setLineWidth(1.4);
  ctx.strokeEllipse(new Rect(p0.x - rr, p0.y - rr, rr * 2, rr * 2));
  ctx.setFillColor(BLACK);
  const dotR = 1.4;
  ctx.fillEllipse(new Rect(p0.x - dotR, p0.y - dotR, dotR * 2, dotR * 2));

  // zodiac signs, on the inside of the loop. Full canvas: all 12, each at
  // its own entry date. Compact canvas: only the current sign, positioned
  // next to the today-marker dot instead of its own (possibly far-away)
  // entry date.
  const zodiacFont = Font.systemFont(8 * scale); // iOS system font covers the astrological Unicode block
  ctx.setFont(zodiacFont);
  ctx.setTextColor(BLACK);
  const drawZodiacGlyph = (glyph, ang, r) => {
    const lp = polarPoint(cx, cy, r - 11 * scale, ang);
    const w = 9 * scale;
    ctx.drawTextInRect(glyph, new Rect(lp.x - w, lp.y - w * 0.7, w * 2, w * 1.4));
  };
  if (zodiacAll) {
    const starts = {};
    for (const [m, d, g] of AstroCore.ZODIAC_SIGNS) starts[`${m}-${d}`] = g;
    yearPoints.forEach((pt, i) => {
      const key = `${pt.date.getUTCMonth() + 1}-${pt.date.getUTCDate()}`;
      if (starts[key]) drawZodiacGlyph(starts[key], angleForIndex(i), eotRadius(pt.eotMinutes));
    });
  } else {
    drawZodiacGlyph(AstroCore.currentZodiacGlyph(today), ang0, r0);
  }
}

// Builds the lit-region path directly for either waxing (side=+1, lit
// limb on the right) or waning (side=-1, lit limb on the left) -- no
// post-hoc mirror/transform needed (Scriptable's DrawContext has no
// transform stack exposed), just bake `side` into the x-coordinate of
// both the limb and terminator arcs. See scriptable/README.md for the
// Node-based geometric validation of this (checks which half of the
// disc ends up lit, and by how much, matching the Python version's
// pixel-count validation from earlier in this project).
function moonLitPath(cx, cy, r, eff, side) {
  const xOff = r * Math.cos(eff); // terminator semi-axis, signed
  const path = new Path();
  const steps = 48;
  for (let i = 0; i <= steps; i++) {
    const t = -Math.PI / 2 + (Math.PI * i) / steps; // top pole -> bottom pole
    const p = new Point(cx + side * r * Math.cos(t), cy + r * Math.sin(t));
    if (i === 0) path.move(p);
    else path.addLine(p);
  }
  for (let i = 0; i <= steps; i++) {
    const t = Math.PI / 2 - (Math.PI * i) / steps; // bottom pole -> top pole
    path.addLine(new Point(cx + side * xOff * Math.cos(t), cy + r * Math.sin(t)));
  }
  path.closeSubpath();
  return path;
}

function drawMoon(ctx, geo, fraction, waxing) {
  const r = geo.rMoon;
  const { cx, cy } = geo;
  const side = waxing ? 1 : -1;

  // Dark base disc.
  ctx.setFillColor(BLACK);
  ctx.fillEllipse(new Rect(cx - r, cy - r, r * 2, r * 2));

  const eff = Math.acos(1 - 2 * Math.min(Math.max(fraction, 0), 1)); // 0..pi, 0=new, pi=full
  const litPath = moonLitPath(cx, cy, r, eff, side);

  ctx.setFillColor(WHITE);
  if (eff <= Math.PI / 2) {
    // Crescent: the lit area IS this lens shape.
    ctx.addPath(litPath);
    ctx.fillPath();
  } else {
    // Gibbous: lit area is the near half-disc PLUS this lens (which now
    // bulges into the FAR half, since cos(eff) < 0 here flips xOff's sign
    // automatically -- see the Node validation in scriptable/README.md).
    const halfPath = new Path();
    const halfX = side > 0 ? cx : cx - r;
    halfPath.addRect(new Rect(halfX, cy - r, r, r * 2));
    ctx.addPath(halfPath);
    ctx.fillPath();
    ctx.addPath(litPath);
    ctx.fillPath();
  }

  ctx.setStrokeColor(BLACK);
  ctx.setLineWidth(1);
  ctx.strokeEllipse(new Rect(cx - r, cy - r, r * 2, r * 2));
}

// ---- text panel ----------------------------------------------------------

function formatHM(date, tzOffsetMinutes) {
  if (!date) return "--";
  const local = new Date(date.getTime() + tzOffsetMinutes * 60000);
  let h = local.getUTCHours();
  const m = local.getUTCMinutes();
  const ampm = h >= 12 ? "pm" : "am";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${String(m).padStart(2, "0")} ${ampm}`;
}

function drawTextPanel(ctx, x, y, w, nowLocal, tzOffsetMinutes, today, times, eotMin, moonName) {
  const eotWord = eotMin > 0 ? "FAST" : "SLOW";
  const eotLine = `${Math.abs(eotMin).toFixed(1)} min ${eotWord}`;
  const dayLenMs = times.sunset && times.sunrise ? times.sunset - times.sunrise : null;
  const dayLenStr = dayLenMs
    ? `${Math.floor(dayLenMs / 3600000)}h ${Math.round((dayLenMs % 3600000) / 60000)}m`
    : "--";

  const dateStr = new Date(nowLocal.getTime() + tzOffsetMinutes * 60000).toLocaleDateString(
    "en-US",
    { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }
  );

  const lines = [
    [dateStr, Font.boldSystemFont(15), 4],
    ["EQUATION OF TIME", Font.systemFont(10), 2],
    [eotLine, Font.boldSystemFont(18), 6],
    ["MOON", Font.systemFont(10), 2],
    [moonName, Font.boldSystemFont(18), 6],
    ["SUN", Font.systemFont(10), 2],
    [`Rise ${formatHM(times.sunrise, tzOffsetMinutes)}  Set ${formatHM(times.sunset, tzOffsetMinutes)}`, Font.systemFont(11), 2],
    [`Day length ${dayLenStr}`, Font.systemFont(11), 2],
    [`Civil twilight ${formatHM(times.dawnCivil, tzOffsetMinutes)}-${formatHM(times.duskCivil, tzOffsetMinutes)}`, Font.systemFont(11), 2],
  ];

  let cursorY = y;
  ctx.setTextColor(BLACK);
  for (const [text, font, gapAfter] of lines) {
    ctx.setFont(font);
    ctx.drawTextInRect(text, new Rect(x, cursorY, w, font.pointSize * 1.4));
    cursorY += font.pointSize * 1.4 + gapAfter;
  }
}

// ---- main render -----------------------------------------------------------

async function renderImage(canvasSize, includeText, lat, lon, tzOffsetMinutes, when) {
  const nowUTC = when || new Date();
  const { today, dayStart } = localCalendarDay(nowUTC, tzOffsetMinutes);
  const geo = makeGeometry(canvasSize);
  const width = includeText ? canvasSize * 2.4 : canvasSize;

  // respectScreenScale must be set immediately after construction, before
  // any other property or drawing call -- Scriptable enforces this at
  // runtime (confirmed on-device: "Cannot change whether to respect the
  // screen scale after performing one of the previous operations").
  //
  // opaque=false with no background fill: this image itself has a
  // transparent backdrop. Confirmed on real hardware that this alone does
  // NOT make the widget see-through, though -- iOS does not support true
  // transparency for Home Screen widgets; it forces its own opaque/light
  // backing behind whatever you draw regardless of alpha. (The "invisible
  // widget" trick some people use fakes it by screenshotting the actual
  // wallpaper and using that as the background image -- not implemented
  // here.) `widget.backgroundColor` in main() is set explicitly instead,
  // to override iOS's forced default (stark white) with something
  // softer; kept the drawn image itself transparent so its circular
  // shape floats on that color rather than sitting in a hard-edged
  // square.
  const ctx = new DrawContext();
  ctx.respectScreenScale = true;
  ctx.size = new Size(width, canvasSize);
  ctx.opaque = false;

  const times = AstroCore.sunTimes(today, lat, lon);
  drawDaylightRing(ctx, geo, dayStart, tzOffsetMinutes, times);

  const yearPoints = AstroCore.eotCalendarYear(today.getUTCFullYear());
  drawEotLoop(ctx, geo, today, yearPoints, includeText);

  const moon = AstroCore.moonIllumination(today);
  drawMoon(ctx, geo, moon.fraction, moon.waxing);

  if (includeText) {
    const eotMin = AstroCore.equationOfTimeMinutes(today);
    const moonName = AstroCore.moonPhaseName(today);
    drawTextPanel(
      ctx,
      canvasSize + 10,
      canvasSize * 0.08,
      width - canvasSize - 20,
      nowUTC,
      tzOffsetMinutes,
      today,
      times,
      eotMin,
      moonName
    );
  }

  return ctx.getImage();
}

async function resolveLocationAndTZ() {
  let lat = FALLBACK_LAT;
  let lon = FALLBACK_LON;
  try {
    Location.setAccuracyToHundredMeters();
    const loc = await Location.current();
    lat = loc.latitude;
    lon = loc.longitude;
  } catch (e) {
    // Location denied/unavailable -- fall back to the hardcoded default.
  }
  // Intl gives the IANA zone name (for display/logging); the actual
  // offset used for date math comes from getTimezoneOffset(), which
  // reflects the DEVICE's system timezone -- same underlying OS setting,
  // so the two agree. getTimezoneOffset() returns UTC-minus-local in
  // minutes (e.g. +240 for EDT); negated, so that
  // `date.getTime() + tzOffsetMinutes*60000` shifts a UTC epoch ms value
  // to local time, matching how hourAngleDeg() and formatHM() use it.
  const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const tzOffsetMinutes = -new Date().getTimezoneOffset();
  return { lat, lon, tzOffsetMinutes, tzName };
}

async function main() {
  const { lat, lon, tzOffsetMinutes } = await resolveLocationAndTZ();

  if (config.runsInWidget) {
    // Only the "small" (square) widget family is actually composed for in
    // this first pass -- the graphic is square, and this always renders a
    // square image regardless of config.widgetFamily. Untested how iOS's
    // ListWidget.backgroundImage handles a square image in a wider
    // "medium"/"large" frame (likely a center-crop, per typical
    // background-image fill behavior, which would just clip the sides of
    // the ring rather than distort it -- but genuinely unverified). Add a
    // text-panel layout for medium/large once the square case is
    // confirmed working on-device.
    const canvasSize = 300;
    const image = await renderImage(canvasSize, false, lat, lon, tzOffsetMinutes);
    const widget = new ListWidget();
    widget.backgroundImage = image;
    // True transparency isn't available (see the DrawContext setup
    // comment in renderImage) -- this softens iOS's forced default
    // (stark white) instead. Pale, slightly cool/blue-tinted to read as
    // "glass" rather than "paper"; adjust the hex directly if it's not
    // the right shade.
    widget.backgroundColor = new Color("#EEF1F4");
    Script.setWidget(widget);
  } else {
    // Running interactively in the app: show the full graphic+text
    // composition (mirrors the Python "full" layout) via Quick Look.
    const image = await renderImage(300, true, lat, lon, tzOffsetMinutes);
    await QuickLook.present(image);
  }
  Script.complete();
}

await main();
