"""Astronomical calculations for the three-ring dashboard.

Equation of Time: Fourier method from
https://equation-of-time.info/calculating-the-equation-of-time
(same formula previously ported to Swift in the Analemma watch app and
verified there to sub-second accuracy against the source).

Sun/twilight and moon phase: astral (pure-Python, no compiled deps).

Zip code resolution: Zippopotam.us (free, no API key) for lat/lon, then
timezonefinder (offline, no API call) for the IANA tz name from those
coordinates -- US zip codes only, matching this project's single-location
scope.
"""
import math
from datetime import date, datetime, timedelta

import requests
from astral import LocationInfo, moon as astral_moon
from astral.sun import sun as astral_sun, dawn as astral_dawn, dusk as astral_dusk
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()


def resolve_zip(zip_code: str) -> tuple[float, float, str]:
    """Return (lat, lon, iana_tzname) for a US zip code."""
    resp = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=10)
    resp.raise_for_status()
    place = resp.json()["places"][0]
    lat, lon = float(place["latitude"]), float(place["longitude"])
    tzname = _tf.timezone_at(lat=lat, lng=lon)
    if tzname is None:
        raise ValueError(f"could not resolve a timezone for zip {zip_code} at ({lat}, {lon})")
    return lat, lon, tzname

SYNODIC_MONTH_DAYS = 29.530588853


def _d2000(d: date) -> float:
    """Days since 2000.0 epoch, per the equation-of-time.info Fourier method.
    Uses local noon (no intraday term) since this module only needs whole-day
    resolution for the EoT ring.
    """
    yyyy, mm, dd = d.year, d.month, d.day
    aaa = 367 * yyyy - 730531.5
    bbb = -round((7 * round(yyyy + (mm + 9) / 12)) / 4)
    ccc = round(275 * mm / 9) + dd
    d_today = 12 / 24  # local noon, tz term dropped (whole-day resolution only)
    return aaa + bbb + ccc + d_today


def equation_of_time_minutes(d: date) -> float:
    """Equation of time in minutes for the given date (positive = sundial fast)."""
    d2000 = _d2000(d)
    cycle = round(d2000 / 365.25)
    theta = 0.0172024 * (d2000 - 365.25 * cycle)
    amp1 = 7.36303 - cycle * 0.00009
    amp2 = 9.92465 - cycle * 0.00014
    phi1 = 3.07892 - cycle * 0.00019
    phi2 = -1.38995 + cycle * 0.00013

    eot1 = amp1 * math.sin(1 * (theta + phi1))
    eot2 = amp2 * math.sin(2 * (theta + phi2))
    eot3 = 0.31730 * math.sin(3 * (theta - 0.94686))
    eot4 = 0.21922 * math.sin(4 * (theta - 0.60716))
    return 0.00526 + eot1 + eot2 + eot3 + eot4


def eot_calendar_year(year: int):
    """List of (day_of_year_index, date, eot_minutes) for Jan 1..Dec 31 of `year`.
    Fixed calendar orientation (Jan 1 = index 0) so the polar loop's rotation
    matches a real calendar wheel rather than drifting with "today".
    """
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    out = []
    d = start
    i = 0
    while d < end:
        out.append((i, d, equation_of_time_minutes(d)))
        d += timedelta(days=1)
        i += 1
    return out


def moon_illumination(d: date) -> tuple[float, bool]:
    """Return (illuminated fraction 0-1, waxing bool) for the given date."""
    age = astral_moon.phase(d)  # 0-27.99, astral's normalized 28-day scale
    phase_angle = 2 * math.pi * age / 28.0
    fraction = (1 - math.cos(phase_angle)) / 2
    waxing = phase_angle <= math.pi
    return fraction, waxing


def moon_phase_name(d: date) -> str:
    age = astral_moon.phase(d)
    # 28-day scale: 0=new,7=first quarter,14=full,21=last quarter
    names = [
        (1.75, "New Moon"),
        (5.25, "Waxing Crescent"),
        (8.75, "First Quarter"),
        (12.25, "Waxing Gibbous"),
        (15.75, "Full Moon"),
        (19.25, "Waning Gibbous"),
        (22.75, "Last Quarter"),
        (26.25, "Waning Crescent"),
        (28.01, "New Moon"),
    ]
    for edge, name in names:
        if age < edge:
            return name
    return "New Moon"


# (start_month, start_day, glyph) for each of the 12 tropical zodiac signs,
# in calendar order starting from Jan 1. Fixed conventional boundary dates
# (they drift by a day across years against the real equinoxes/solstices --
# not worth chasing precision for a decorative marker). This is the sign's
# ENTRY date, distinct from the calendar month-start dates used for the
# EoT loop's dots.
ZODIAC_SIGNS = [
    (1, 20, "♒"),  # Aquarius
    (2, 19, "♓"),  # Pisces
    (3, 21, "♈"),  # Aries
    (4, 20, "♉"),  # Taurus
    (5, 21, "♊"),  # Gemini
    (6, 21, "♋"),  # Cancer
    (7, 23, "♌"),  # Leo
    (8, 23, "♍"),  # Virgo
    (9, 23, "♎"),  # Libra
    (10, 23, "♏"),  # Scorpio
    (11, 22, "♐"),  # Sagittarius
    (12, 22, "♑"),  # Capricorn
]


def current_zodiac_glyph(d: date) -> str:
    """Glyph for whichever zodiac sign's date range contains `d`."""
    md = (d.month, d.day)
    active = ZODIAC_SIGNS[-1][2]  # Capricorn wraps around into Jan 1-19
    for month, day, glyph in ZODIAC_SIGNS:
        if md >= (month, day):
            active = glyph
        else:
            break
    return active


def sun_times(d: date, lat: float, lon: float, tzname: str) -> dict:
    """Sunrise/sunset + civil/nautical/astronomical dawn/dusk, all tz-aware."""
    loc = LocationInfo("", "", tzname, lat, lon)
    base = astral_sun(loc.observer, date=d, tzinfo=loc.timezone)
    result = {
        "sunrise": base["sunrise"],
        "sunset": base["sunset"],
        "noon": base["noon"],
        "dawn_civil": base["dawn"],
        "dusk_civil": base["dusk"],
    }
    for depression, prefix in ((12, "nautical"), (18, "astronomical")):
        result[f"dawn_{prefix}"] = astral_dawn(loc.observer, date=d, tzinfo=loc.timezone, depression=depression)
        result[f"dusk_{prefix}"] = astral_dusk(loc.observer, date=d, tzinfo=loc.timezone, depression=depression)
    return result
