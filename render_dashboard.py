"""Renders the three-ring astronomy dashboard PNG for TRMNL, at any of the
four standard TRMNL layout sizes (full / half_horizontal / half_vertical /
quadrant).

Rings, centered circle, radii scale per layout (see LAYOUTS below):
  - moon phase disc              (center)
  - equation-of-time loop         (polar plot, one point per day, Jan 1 at top)
  - daylight/twilight/night ring  (24h clock face, noon at top, midnight at bottom)
Text panel (date/EoT/moon/sun) sits beside or below the graphic, except in
the quadrant layout which is graphic-only.

Design is pure black/white/gray with no photographic content, so the
image is left as 8-bit grayscale (antialiased) for TRMNL's own pipeline
to dither -- consistent with how it already renders every other Liquid
element on the device. The twilight bands are diagonal hatch patterns
rather than flat grays for the same reason the moon crescent works: pure
black/white content survives both dithering and naive thresholding
identically, where a flat mid-gray fill can collapse to solid black or
vanish to white under a simple threshold.
"""
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageChops

from astro_core import equation_of_time_minutes, eot_calendar_year, moon_illumination, moon_phase_name, resolve_zip, sun_times

SS = 4  # supersample factor

BLACK = 0
WHITE = 255

# Reference geometry (the "full" layout's ring radii, in final unsupersampled
# px) that every other layout's radii are derived from, proportional to its
# own r_ring_out. Font sizes and stroke widths are NOT scaled per layout --
# they're physical pixel sizes on one fixed device panel, same reasoning as
# not scaling font size just because a browser window got smaller.
_REF_R_RING_OUT = 215
_REF_R_RING_IN = 185
_REF_R_EOT_BASE = 120
_REF_R_EOT_AMP = 2.727  # px per EoT-minute
_REF_R_MOON = 55


class Geometry:
    def __init__(self, cx, cy, r_ring_out):
        scale = r_ring_out / _REF_R_RING_OUT
        self.scale = scale  # for radial clearances/offsets -- NOT for font size or stroke width
        self.cx = cx * SS
        self.cy = cy * SS
        self.r_ring_out = r_ring_out * SS
        self.r_ring_in = _REF_R_RING_IN * scale * SS
        self.r_eot_base = _REF_R_EOT_BASE * scale * SS
        self.r_eot_amp = _REF_R_EOT_AMP * scale * SS
        self.r_moon = _REF_R_MOON * scale * SS


# (canvas_w, canvas_h, circle_cx, circle_cy, r_ring_out, text_mode, text_x, text_y, text_w, compact)
# text_mode is "right", "below", or None (graphic only, e.g. quadrant). compact
# drops the SUN block -- half sizes don't have the vertical room for it at
# full-size, unscaled fonts.
LAYOUTS = {
    "full": dict(w=800, h=480, cx=240, cy=240, r_ring_out=215, text_mode="right", text_x=500, text_y=40, text_w=280, compact=False),
    "half_horizontal": dict(w=800, h=240, cx=130, cy=120, r_ring_out=105, text_mode="right", text_x=280, text_y=14, text_w=500, compact=True),
    "half_vertical": dict(w=400, h=480, cx=200, cy=155, r_ring_out=135, text_mode="below", text_x=40, text_y=310, text_w=320, compact=True),
    "quadrant": dict(w=400, h=240, cx=200, cy=120, r_ring_out=100, text_mode=None, text_x=None, text_y=None, text_w=None, compact=False),
}

# Body text is serif. The zodiac glyphs (U+2648-2653) are a separate,
# dedicated symbol font, NOT a fallback in the same chain -- DejaVu Serif
# (like most serif text faces) simply doesn't include the astrological
# symbol block, confirmed by rendering all 12 and getting tofu boxes.
# DejaVu Sans does have them, so the ring's zodiac labels use it regardless
# of which serif face is chosen for everything else.
FONT_CANDIDATES_REGULAR = [
    os.environ.get("FONT_REGULAR", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/opt/homebrew/Library/Homebrew/vendor/portable-ruby/4.0.5_1/lib/ruby/gems/4.0.0/gems/rdoc-7.0.4/lib/rdoc/generator/template/darkfish/fonts/Lato-Regular.ttf",
]
FONT_CANDIDATES_BOLD = [
    os.environ.get("FONT_BOLD", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
FONT_CANDIDATES_SYMBOL = [
    os.environ.get("FONT_SYMBOL", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(candidates, size):
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    return None


def font(size, bold=False):
    px = size * SS
    if bold:
        f = _load_font(FONT_CANDIDATES_BOLD, px)
        if f:
            return f
    f = _load_font(FONT_CANDIDATES_REGULAR, px)
    if f:
        return f
    return ImageFont.load_default()


def symbol_font(size):
    px = size * SS
    f = _load_font(FONT_CANDIDATES_SYMBOL, px)
    if f:
        return f
    return font(size)


def hour_angle_deg(dt_local: datetime) -> float:
    """Degrees clockwise from top (=noon) for a local datetime's time-of-day.
    Noon at top (12 o'clock), midnight at bottom (6 o'clock).
    """
    secs = dt_local.hour * 3600 + dt_local.minute * 60 + dt_local.second
    secs_from_noon = (secs - 12 * 3600) % 86400
    return secs_from_noon / 86400 * 360.0


def day_angle_deg(day_of_year_offset_frac: float) -> float:
    """Degrees clockwise from top (=Jan 1) for a fractional position in the year."""
    return day_of_year_offset_frac * 360.0


def polar_point(cx, cy, r, angle_deg):
    """angle_deg measured clockwise from straight up (12 o'clock)."""
    rad = math.radians(angle_deg - 90)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def hatch_wedge(img: Image.Image, bbox, a0, a1, spacing):
    """Fill a pie-slice wedge (PIL angle convention, degrees) with a diagonal-line
    hatch instead of a flat gray. Pure black/white lines survive both dithering
    and naive thresholding identically -- a flat mid-gray fill does not (it can
    collapse to solid black or vanish to white under a simple threshold).
    """
    size = img.size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).pieslice(bbox, a0, a1, fill=255)

    hatch = Image.new("L", size, WHITE)
    hd = ImageDraw.Draw(hatch)
    diag = int(math.hypot(*size))
    for offset in range(0, 2 * diag, spacing):
        hd.line([(offset - diag, 0), (offset, diag)], fill=BLACK, width=max(1, SS // 2))

    img.paste(hatch, (0, 0), mask)


def draw_daylight_ring(img: Image.Image, draw: ImageDraw.ImageDraw, geo: Geometry, now_local: datetime, times: dict):
    """24h clock-face ring, noon at top, clockwise. Night/day are flat
    black/white; the three twilight stages are diagonal hatch patterns
    (densest near night, sparsest near day) rather than flat grays.
    """
    day0 = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    def a(dt):
        return hour_angle_deg(dt)

    # (start, end, fill) for solid bands, or (start, end, None, spacing) for hatch
    bands = [
        (day0, times["dawn_astronomical"], BLACK, None),
        (times["dawn_astronomical"], times["dawn_nautical"], None, 5 * SS),
        (times["dawn_nautical"], times["dawn_civil"], None, 9 * SS),
        (times["dawn_civil"], times["sunrise"], None, 15 * SS),
        (times["sunrise"], times["sunset"], WHITE, None),
        (times["sunset"], times["dusk_civil"], None, 15 * SS),
        (times["dusk_civil"], times["dusk_nautical"], None, 9 * SS),
        (times["dusk_nautical"], times["dusk_astronomical"], None, 5 * SS),
        (times["dusk_astronomical"], day0 + timedelta(days=1), BLACK, None),
    ]

    cx, cy, r_out, r_in = geo.cx, geo.cy, geo.r_ring_out, geo.r_ring_in
    bbox = (cx - r_out, cy - r_out, cx + r_out, cy + r_out)
    for start, end, fill, spacing in bands:
        a0, a1 = a(start), a(end)
        if a1 <= a0:
            a1 += 360
        # pieslice angles: 0deg = 3 o'clock in PIL convention, clockwise positive;
        # our a() is clockwise-from-top, so shift by -90.
        if fill is not None:
            draw.pieslice(bbox, a0 - 90, a1 - 90, fill=fill)
        else:
            hatch_wedge(img, bbox, a0 - 90, a1 - 90, spacing)

    # punch the inner hole so only the annulus remains
    inner_bbox = (cx - r_in, cy - r_in, cx + r_in, cy + r_in)
    draw.ellipse(inner_bbox, fill=WHITE)

    # crisp edge circles
    draw.ellipse(bbox, outline=BLACK, width=SS)
    draw.ellipse(inner_bbox, outline=BLACK, width=SS)

    # hour ticks (every 3h, longer at 0/6/12/18) + "now" marker
    scale = geo.scale
    for h in range(24):
        tick_dt = day0.replace(hour=h)
        ang = a(tick_dt)
        long_tick = h % 6 == 0
        r0 = r_in - (14 * scale if long_tick else 6 * scale) * SS
        p0 = polar_point(cx, cy, r0, ang)
        p1 = polar_point(cx, cy, r_in, ang)
        draw.line([p0, p1], fill=BLACK, width=SS)

    now_ang = a(now_local)
    tip = polar_point(cx, cy, r_out + 2 * scale * SS, now_ang)
    base_l = polar_point(cx, cy, r_out + 16 * scale * SS, now_ang - 3)
    base_r = polar_point(cx, cy, r_out + 16 * scale * SS, now_ang + 3)
    draw.polygon([tip, base_l, base_r], fill=BLACK)

    # noon / midnight anchor labels, just inside the ring. Nudged off the
    # exact 0/180 axis so they don't sit radially under the Jan/Jul zodiac
    # glyphs on the EoT loop, which are also anchored at 0/180. Below a
    # certain ring size there just isn't room for an 8-letter word next to
    # a zodiac glyph at fixed (unscaled) font size -- the long tick marks
    # at true 0/180 already mark noon/midnight, so skip the words there.
    if scale >= 0.9:
        f = font(11)
        for label, ang in (("NOON", 25), ("MIDNIGHT", 205)):
            p = polar_point(cx, cy, r_in - 28 * scale * SS, ang)
            bbox2 = draw.textbbox((0, 0), label, font=f)
            w, h = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
            draw.text((p[0] - w / 2, p[1] - h / 2), label, fill=BLACK, font=f)


MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Tropical zodiac sign in effect on the 1st of each month (Northern convention).
ZODIAC_GLYPH = ["♑", "♒", "♓", "♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐"]
CARDINAL_MONTHS = {0, 3, 6, 9}  # Jan, Apr, Jul, Oct


def draw_eot_loop(draw: ImageDraw.ImageDraw, geo: Geometry, today, year_points):
    cx, cy = geo.cx, geo.cy

    def eot_radius(eot_min):
        return geo.r_eot_base + eot_min * geo.r_eot_amp

    year_len = len(year_points)

    def angle_for_index(i):
        return day_angle_deg(i / year_len)

    # 0-min reference circle + +-10min guide circles
    r_base = geo.r_eot_base
    draw.ellipse((cx - r_base, cy - r_base, cx + r_base, cy + r_base), outline=160, width=max(1, SS // 2))
    for guide in (-10, 10):
        r = eot_radius(guide)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=200, width=max(1, SS // 2))

    pts = []
    today_idx = 0
    for i, (doy, d, eot_min) in enumerate(year_points):
        ang = angle_for_index(i)
        r = eot_radius(eot_min)
        pts.append(polar_point(cx, cy, r, ang))
        if d == today:
            today_idx = i
    draw.line(pts + [pts[0]], fill=BLACK, width=int(2.2 * SS), joint="curve")

    # month start tick marks (all 12) + zodiac sign at the 4 cardinal months
    scale = geo.scale
    dot_r = max(2 * SS, 3 * scale * SS)
    f_month = symbol_font(13)
    for i, (doy, dd, eot_min) in enumerate(year_points):
        if dd.day == 1:
            ang = angle_for_index(i)
            r = eot_radius(eot_min)
            p = polar_point(cx, cy, r, ang)
            draw.ellipse((p[0] - dot_r, p[1] - dot_r, p[0] + dot_r, p[1] + dot_r), fill=BLACK)
            if (dd.month - 1) in CARDINAL_MONTHS:
                lp = polar_point(cx, cy, r + 22 * scale * SS, ang)
                label = ZODIAC_GLYPH[dd.month - 1]
                bbox = draw.textbbox((0, 0), label, font=f_month)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((lp[0] - w / 2, lp[1] - h / 2), label, fill=BLACK, font=f_month)

    # today marker (open ring)
    ang0 = angle_for_index(today_idx)
    r0 = eot_radius(year_points[today_idx][2])
    p = polar_point(cx, cy, r0, ang0)
    rr = max(4 * SS, 7 * scale * SS)
    draw.ellipse((p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr), outline=BLACK, width=int(2 * SS))
    draw.ellipse((p[0] - 2 * SS, p[1] - 2 * SS, p[0] + 2 * SS, p[1] + 2 * SS), fill=BLACK)


def draw_moon(draw_target: Image.Image, geo: Geometry, fraction: float, waxing: bool):
    r = geo.r_moon
    size = int(r * 2 + 4 * SS)
    disc = Image.new("L", (size, size), WHITE)
    c = size / 2
    bbox = (c - r, c - r, c + r, c + r)

    phase_angle = math.acos(1 - 2 * fraction) if fraction <= 1 else math.pi
    eff = phase_angle  # 0..pi, 0=new,pi=full (waxing convention; mirrored for waning below)
    x = r * math.cos(eff)  # ellipse horizontal semi-axis, signed

    right_half = Image.new("L", (size, size), BLACK)
    ImageDraw.Draw(right_half).rectangle((c, 0, size, size), fill=WHITE)
    left_half = ImageChops.invert(right_half)

    ell = Image.new("L", (size, size), BLACK)
    ImageDraw.Draw(ell).ellipse((c - abs(x), c - r, c + abs(x), c + r), fill=WHITE)

    if eff <= math.pi / 2:
        lit = ImageChops.darker(right_half, ImageChops.invert(ell))
    else:
        lit = ImageChops.lighter(right_half, ImageChops.darker(left_half, ell))

    if not waxing:
        lit = lit.transpose(Image.FLIP_LEFT_RIGHT)

    disc_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(disc_mask).ellipse(bbox, fill=255)
    dark_base = Image.new("L", (size, size), 0)
    white_full = Image.new("L", (size, size), WHITE)
    disc = Image.composite(white_full, dark_base, ImageChops.darker(lit, disc_mask))
    disc = Image.composite(disc, white_full, disc_mask)

    d = ImageDraw.Draw(disc)
    d.ellipse(bbox, outline=BLACK, width=SS)

    draw_target.paste(disc, (int(geo.cx - c), int(geo.cy - c)), disc_mask)


def format_hm(dt):
    return dt.strftime("%-I:%M %p").lower()


def draw_text_panel(draw, tx, ty, tw, now_local, today, times, eot_min, fraction, center=False, compact=False):
    """compact=True drops the SUN block (rise/set/day-length/twilight) for
    layouts too short to fit the full text stack (half_horizontal,
    half_vertical) -- font sizes stay fixed either way, since they're
    physical pixel sizes on a fixed device panel, not something that
    should shrink just because a smaller layout was picked.
    """
    f_title = font(22, bold=True)
    f_label = font(15)
    f_value = font(28, bold=True)
    f_small = font(13)

    eot_word = "FAST" if eot_min > 0 else "SLOW"
    eot_line = f"{abs(eot_min):.1f} min {eot_word}"
    day_len = times["sunset"] - times["sunrise"]
    day_len_h = day_len.seconds // 3600
    day_len_m = (day_len.seconds % 3600) // 60

    lines = [
        (now_local.strftime("%A, %B %-d, %Y"), f_title, 0),
        ("", f_small, 6),
        ("EQUATION OF TIME", f_label, 10),
        (eot_line, f_value, 2),
        ("", f_small, 10),
        ("MOON", f_label, 10),
        (moon_phase_name(today), f_value, 2),
    ]
    if not compact:
        lines += [
            ("", f_small, 10),
            ("SUN", f_label, 10),
            (f"Rise {format_hm(times['sunrise'])}  Set {format_hm(times['sunset'])}", f_small, 4),
            (f"Day length {day_len_h}h {day_len_m}m", f_small, 4),
            (f"Civil twilight {format_hm(times['dawn_civil'])}–{format_hm(times['dusk_civil'])}", f_small, 4),
        ]
    y = ty
    for text, fnt, gap_after in lines:
        if not text:
            y += gap_after * SS
            continue
        if center:
            bbox = draw.textbbox((0, 0), text, font=fnt)
            w = bbox[2] - bbox[0]
            x = tx + (tw - w) / 2
        else:
            x = tx
        draw.text((x, y), text, fill=BLACK, font=fnt)
        bbox = draw.textbbox((x, y), text, font=fnt)
        y = bbox[3] + gap_after * SS


def render(lat, lon, tzname, out_path, layout="full", when=None):
    cfg = LAYOUTS[layout]
    W, H = cfg["w"], cfg["h"]
    geo = Geometry(cfg["cx"], cfg["cy"], cfg["r_ring_out"])

    tz = ZoneInfo(tzname)
    now_local = (when or datetime.now(timezone.utc)).astimezone(tz)
    today = now_local.date()

    img = Image.new("L", (W * SS, H * SS), WHITE)
    draw = ImageDraw.Draw(img)

    times = sun_times(today, lat, lon, tzname)
    draw_daylight_ring(img, draw, geo, now_local, times)

    year_points = eot_calendar_year(today.year)
    draw_eot_loop(draw, geo, today, year_points)

    fraction, waxing = moon_illumination(today)
    draw_moon(img, geo, fraction, waxing)
    draw = ImageDraw.Draw(img)

    if cfg["text_mode"] is not None:
        eot_min = equation_of_time_minutes(today)
        tx, ty, tw = cfg["text_x"] * SS, cfg["text_y"] * SS, cfg["text_w"] * SS
        draw_text_panel(
            draw, tx, ty, tw, now_local, today, times, eot_min, fraction,
            center=(cfg["text_mode"] == "below"), compact=cfg["compact"],
        )

    final = img.resize((W, H), Image.LANCZOS)
    final.save(out_path)
    return out_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--zip", dest="zip_code", help="US zip code -- resolves lat/lon/tz, overrides --lat/--lon/--tz")
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("--tz")
    p.add_argument("--layout", choices=list(LAYOUTS), default="full")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    if args.zip_code:
        lat, lon, tzname = resolve_zip(args.zip_code)
        print(f"resolved zip {args.zip_code} -> lat={lat} lon={lon} tz={tzname}")
    elif args.lat is not None and args.lon is not None and args.tz:
        lat, lon, tzname = args.lat, args.lon, args.tz
    else:
        p.error("either --zip, or all of --lat/--lon/--tz, is required")

    out = args.out or f"data/dashboard_{args.layout}.png"
    render(lat, lon, tzname, out, layout=args.layout)
    print("wrote", out)
