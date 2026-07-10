"""Renders the three-ring astronomy dashboard PNG for TRMNL.

Layout (centered circle, radii in final 800x480 px):
  - moon phase disc            r 0-55      (center)
  - equation-of-time loop       r ~75-165   (polar plot, one point per day)
  - daylight/twilight/night ring r 185-215  (24h clock face, midnight at top)
Text panel fills the right-hand side.

Design is pure black/white/gray with no photographic content, so the
image is left as 8-bit grayscale (antialiased) for TRMNL's own pipeline
to dither -- consistent with how it already renders every other Liquid
element on the device.
"""
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageChops

from astro_core import equation_of_time_minutes, eot_calendar_year, moon_illumination, moon_phase_name, sun_times

W, H = 800, 480
SS = 4  # supersample factor
CX, CY = 240 * SS, 240 * SS
R_RING_OUT = 215 * SS
R_RING_IN = 185 * SS
R_EOT_BASE = 120 * SS
R_EOT_AMP_PX_PER_MIN = 2.727 * SS
R_MOON = 55 * SS

BLACK = 0
WHITE = 255

FONT_CANDIDATES_REGULAR = [
    os.environ.get("FONT_REGULAR", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/opt/homebrew/Library/Homebrew/vendor/portable-ruby/4.0.5_1/lib/ruby/gems/4.0.0/gems/rdoc-7.0.4/lib/rdoc/generator/template/darkfish/fonts/Lato-Regular.ttf",
]
FONT_CANDIDATES_BOLD = [
    os.environ.get("FONT_BOLD", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
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


def hour_angle_deg(dt_local: datetime) -> float:
    """Degrees clockwise from top (=midnight) for a local datetime's time-of-day."""
    frac = (dt_local.hour * 3600 + dt_local.minute * 60 + dt_local.second) / 86400
    return frac * 360.0


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


def draw_daylight_ring(img: Image.Image, draw: ImageDraw.ImageDraw, now_local: datetime, times: dict):
    """24h clock-face ring, midnight at top, clockwise. Night/day are flat
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

    bbox = (CX - R_RING_OUT, CY - R_RING_OUT, CX + R_RING_OUT, CY + R_RING_OUT)
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
    inner_bbox = (CX - R_RING_IN, CY - R_RING_IN, CX + R_RING_IN, CY + R_RING_IN)
    draw.ellipse(inner_bbox, fill=WHITE)

    # crisp edge circles
    draw.ellipse(bbox, outline=BLACK, width=SS)
    draw.ellipse(inner_bbox, outline=BLACK, width=SS)

    # hour ticks (every 3h, longer at 0/6/12/18) + "now" marker
    for h in range(24):
        ang = h / 24 * 360
        long_tick = h % 6 == 0
        r0 = R_RING_IN - (14 * SS if long_tick else 6 * SS)
        p0 = polar_point(CX, CY, r0, ang)
        p1 = polar_point(CX, CY, R_RING_IN, ang)
        draw.line([p0, p1], fill=BLACK, width=SS)

    now_ang = a(now_local)
    tip = polar_point(CX, CY, R_RING_OUT + 16 * SS, now_ang)
    base_l = polar_point(CX, CY, R_RING_OUT + 2 * SS, now_ang - 3)
    base_r = polar_point(CX, CY, R_RING_OUT + 2 * SS, now_ang + 3)
    draw.polygon([tip, base_l, base_r], fill=BLACK)

    # noon / midnight anchor labels, just inside the ring
    f = font(11)
    for label, ang in (("MIDNIGHT", 0), ("NOON", 180)):
        p = polar_point(CX, CY, R_RING_IN - 28 * SS, ang)
        bbox = draw.textbbox((0, 0), label, font=f)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((p[0] - w / 2, p[1] - h / 2), label, fill=BLACK, font=f)


MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CARDINAL_MONTHS = {0, 3, 6, 9}  # Jan, Apr, Jul, Oct


def draw_eot_loop(draw: ImageDraw.ImageDraw, today, year_points):
    def eot_radius(eot_min):
        return R_EOT_BASE + eot_min * R_EOT_AMP_PX_PER_MIN

    year_len = len(year_points)

    def angle_for_index(i):
        return day_angle_deg(i / year_len)

    # 0-min reference circle + +-10min guide circles
    draw.ellipse(
        (CX - R_EOT_BASE, CY - R_EOT_BASE, CX + R_EOT_BASE, CY + R_EOT_BASE),
        outline=160,
        width=max(1, SS // 2),
    )
    for guide in (-10, 10):
        r = eot_radius(guide)
        draw.ellipse((CX - r, CY - r, CX + r, CY + r), outline=200, width=max(1, SS // 2))

    pts = []
    today_idx = 0
    for i, (doy, d, eot_min) in enumerate(year_points):
        ang = angle_for_index(i)
        r = eot_radius(eot_min)
        pts.append(polar_point(CX, CY, r, ang))
        if d == today:
            today_idx = i
    draw.line(pts + [pts[0]], fill=BLACK, width=int(2.2 * SS), joint="curve")

    # month start tick marks + cardinal month labels
    f_month = font(12)
    for i, (doy, dd, eot_min) in enumerate(year_points):
        if dd.day == 1:
            ang = angle_for_index(i)
            r = eot_radius(eot_min)
            p = polar_point(CX, CY, r, ang)
            draw.ellipse((p[0] - 3 * SS, p[1] - 3 * SS, p[0] + 3 * SS, p[1] + 3 * SS), fill=BLACK)
            if (dd.month - 1) in CARDINAL_MONTHS:
                lp = polar_point(CX, CY, r + 16 * SS, ang)
                label = MONTH_ABBR[dd.month - 1]
                bbox = draw.textbbox((0, 0), label, font=f_month)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((lp[0] - w / 2, lp[1] - h / 2), label, fill=BLACK, font=f_month)

    # today marker (open ring)
    ang0 = angle_for_index(today_idx)
    r0 = eot_radius(year_points[today_idx][2])
    p = polar_point(CX, CY, r0, ang0)
    rr = 7 * SS
    draw.ellipse((p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr), outline=BLACK, width=int(2 * SS))
    draw.ellipse((p[0] - 2 * SS, p[1] - 2 * SS, p[0] + 2 * SS, p[1] + 2 * SS), fill=BLACK)


def draw_moon(draw_target: Image.Image, fraction: float, waxing: bool):
    r = R_MOON
    size = r * 2 + 4 * SS
    disc = Image.new("L", (size, size), WHITE)
    d = ImageDraw.Draw(disc)
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

    draw_target.paste(disc, (int(CX - c), int(CY - c)), disc_mask)


def format_hm(dt):
    return dt.strftime("%-I:%M %p").lower()


def render(lat, lon, tzname, out_path, when=None):
    tz = ZoneInfo(tzname)
    now_local = (when or datetime.now(timezone.utc)).astimezone(tz)
    today = now_local.date()

    img = Image.new("L", (W * SS, H * SS), WHITE)
    draw = ImageDraw.Draw(img)

    times = sun_times(today, lat, lon, tzname)
    draw_daylight_ring(img, draw, now_local, times)

    year_points = eot_calendar_year(today.year)
    draw_eot_loop(draw, today, year_points)

    fraction, waxing = moon_illumination(today)
    draw_moon(img, fraction, waxing)
    draw = ImageDraw.Draw(img)

    # --- text panel ---
    tx = 500 * SS
    ty = 40 * SS
    f_title = font(22, bold=True)
    f_label = font(15)
    f_value = font(28, bold=True)
    f_small = font(13)

    eot_min = equation_of_time_minutes(today)
    eot_sign = "fast" if eot_min > 0 else "slow"
    day_len = times["sunset"] - times["sunrise"]
    day_len_h = day_len.seconds // 3600
    day_len_m = (day_len.seconds % 3600) // 60

    lines = [
        (now_local.strftime("%A, %B %-d, %Y"), f_title, 0),
        ("", f_small, 6),
        ("EQUATION OF TIME", f_label, 10),
        (f"{eot_min:+.1f} min ({eot_sign})", f_value, 2),
        ("", f_small, 10),
        ("MOON", f_label, 10),
        (f"{moon_phase_name(today)} · {fraction*100:.0f}%", f_value, 2),
        ("", f_small, 10),
        ("SUN", f_label, 10),
        (f"Rise {format_hm(times['sunrise'])}  Set {format_hm(times['sunset'])}", f_small, 4),
        (f"Day length {day_len_h}h {day_len_m}m", f_small, 4),
        (f"Civil twilight {format_hm(times['dawn_civil'])}–{format_hm(times['dusk_civil'])}", f_small, 4),
    ]
    y = ty
    for text, fnt, gap_after in lines:
        if text:
            draw.text((tx, y), text, fill=BLACK, font=fnt)
            bbox = draw.textbbox((tx, y), text, font=fnt)
            y = bbox[3] + gap_after * SS
        else:
            y += gap_after * SS

    final = img.resize((W, H), Image.LANCZOS)
    final.save(out_path)
    return out_path


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--tz", required=True)
    p.add_argument("--out", default="data/dashboard.png")
    args = p.parse_args()
    render(args.lat, args.lon, args.tz, args.out)
    print("wrote", args.out)
