// Astro Core -- astronomy math shared by the Scriptable widget script.
// Pure JS, no dependencies -- ports astro_core.py's math to run entirely
// on-device (no zip geocoding needed here; the widget script supplies
// lat/lon/tz directly from the phone's own Location/Intl APIs).
//
// Equation of Time: Fourier method from
// https://equation-of-time.info/calculating-the-equation-of-time
// (same formula as the Python version, verified there against known
// extrema and previously in a Swift watch app).
//
// Solar declination: Spencer (1971) Fourier series -- the same paper
// equation-of-time.info's own method is built on, so this stays
// consistent with the EoT formula above rather than mixing lineages.
//
// Sunrise/sunset/twilight: standard NOAA solar-position hour-angle
// method, built from the declination + EoT above.
//
// Moon phase: synodic-month age from a known reference new moon, not
// astral's specific 28-day-normalized scale (that scale is a small
// implementation detail of the Python `astral` package, not a real
// astronomical constant) -- expect illumination % to differ from the
// Python version by up to a percent or two on any given day. Neither is
// precision timekeeping; both are decorative.

function daysSinceEpoch2000(date) {
  // Mirrors astro_core.py's _d2000: days since 2000.0, whole-day
  // resolution (local noon, no intraday term).
  const yyyy = date.getUTCFullYear();
  const mm = date.getUTCMonth() + 1;
  const dd = date.getUTCDate();
  const aaa = 367 * yyyy - 730531.5;
  const bbb = -Math.round((7 * Math.round(yyyy + (mm + 9) / 12)) / 4);
  const ccc = Math.round((275 * mm) / 9) + dd;
  const dToday = 12 / 24;
  return aaa + bbb + ccc + dToday;
}

function equationOfTimeMinutes(date) {
  const d2000 = daysSinceEpoch2000(date);
  const cycle = Math.round(d2000 / 365.25);
  const theta = 0.0172024 * (d2000 - 365.25 * cycle);
  const amp1 = 7.36303 - cycle * 0.00009;
  const amp2 = 9.92465 - cycle * 0.00014;
  const phi1 = 3.07892 - cycle * 0.00019;
  const phi2 = -1.38995 + cycle * 0.00013;

  const eot1 = amp1 * Math.sin(1 * (theta + phi1));
  const eot2 = amp2 * Math.sin(2 * (theta + phi2));
  const eot3 = 0.3173 * Math.sin(3 * (theta - 0.94686));
  const eot4 = 0.21922 * Math.sin(4 * (theta - 0.60716));
  return 0.00526 + eot1 + eot2 + eot3 + eot4;
}

function dayOfYearUTC(date) {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  const today = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  return Math.round((today - start) / 86400000) + 1; // 1-indexed, Jan 1 = 1
}

function solarDeclinationRad(date) {
  // Spencer (1971), fractional-year gamma in radians.
  const dayOfYear = dayOfYearUTC(date);
  const daysInYear = ((date.getUTCFullYear() % 4 === 0 && date.getUTCFullYear() % 100 !== 0) || date.getUTCFullYear() % 400 === 0) ? 366 : 365;
  const gamma = ((2 * Math.PI) / daysInYear) * (dayOfYear - 1);
  return (
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma)
  );
}

function toRad(deg) {
  return (deg * Math.PI) / 180;
}
function toDeg(rad) {
  return (rad * 180) / Math.PI;
}

// Returns the UTC Date for the event (sunrise/sunset/dawn/dusk at a given
// depression angle below horizon, in degrees; 0 = true horizon, positive
// = below horizon e.g. 6/12/18 for civil/nautical/astronomical) on the
// given calendar date (interpreted at local noon for the day/EoT lookup),
// or null if the sun never crosses that depression that day (polar
// day/night) -- `rising`: true for the morning event, false for evening.
function sunEventUTC(date, lat, lon, depressionDeg, rising) {
  const decl = solarDeclinationRad(date);
  const latRad = toRad(lat);
  const eotMin = equationOfTimeMinutes(date);

  const cosH =
    (Math.sin(toRad(-depressionDeg)) - Math.sin(latRad) * Math.sin(decl)) /
    (Math.cos(latRad) * Math.cos(decl));
  if (cosH > 1 || cosH < -1) return null; // never reaches this depression today

  const hourAngleDeg = toDeg(Math.acos(cosH)); // 0..180
  // Solar noon in UTC minutes-of-day: 12:00 local mean solar time, minus
  // longitude correction, minus the equation-of-time correction (EoT
  // positive = sundial fast = true solar noon earlier than mean).
  const solarNoonUTCMinutes = 12 * 60 - lon * 4 - eotMin;
  const offsetMinutes = hourAngleDeg * 4; // 4 minutes per degree of hour angle
  const eventUTCMinutes = rising
    ? solarNoonUTCMinutes - offsetMinutes
    : solarNoonUTCMinutes + offsetMinutes;

  const dayStartUTC = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  return new Date(dayStartUTC + eventUTCMinutes * 60000);
}

function sunTimes(date, lat, lon) {
  return {
    sunrise: sunEventUTC(date, lat, lon, 0.833, true), // standard refraction+radius correction
    sunset: sunEventUTC(date, lat, lon, 0.833, false),
    dawnCivil: sunEventUTC(date, lat, lon, 6, true),
    duskCivil: sunEventUTC(date, lat, lon, 6, false),
    dawnNautical: sunEventUTC(date, lat, lon, 12, true),
    duskNautical: sunEventUTC(date, lat, lon, 12, false),
    dawnAstronomical: sunEventUTC(date, lat, lon, 18, true),
    duskAstronomical: sunEventUTC(date, lat, lon, 18, false),
  };
}

const SYNODIC_MONTH_DAYS = 29.530588853;
const KNOWN_NEW_MOON_UTC = Date.UTC(2000, 0, 6, 18, 14); // a known new moon reference

function moonAgeDays(date) {
  const diffDays = (date.getTime() - KNOWN_NEW_MOON_UTC) / 86400000;
  let age = diffDays % SYNODIC_MONTH_DAYS;
  if (age < 0) age += SYNODIC_MONTH_DAYS;
  return age;
}

function moonIllumination(date) {
  const age = moonAgeDays(date);
  const phaseAngle = (2 * Math.PI * age) / SYNODIC_MONTH_DAYS;
  const fraction = (1 - Math.cos(phaseAngle)) / 2;
  const waxing = phaseAngle <= Math.PI;
  return { fraction, waxing };
}

function moonPhaseName(date) {
  const age = moonAgeDays(date);
  const edges = [
    [1.84, "New Moon"],
    [5.53, "Waxing Crescent"],
    [9.22, "First Quarter"],
    [12.91, "Waxing Gibbous"],
    [16.61, "Full Moon"],
    [20.3, "Waning Gibbous"],
    [23.99, "Last Quarter"],
    [27.68, "Waning Crescent"],
    [SYNODIC_MONTH_DAYS + 0.01, "New Moon"],
  ];
  for (const [edge, name] of edges) {
    if (age < edge) return name;
  }
  return "New Moon";
}

// (start_month, start_day, glyph) for each of the 12 tropical zodiac
// signs' entry dates -- same conventional fixed boundary dates as
// astro_core.py's ZODIAC_SIGNS.
const ZODIAC_SIGNS = [
  [1, 20, "♒"], // Aquarius
  [2, 19, "♓"], // Pisces
  [3, 21, "♈"], // Aries
  [4, 20, "♉"], // Taurus
  [5, 21, "♊"], // Gemini
  [6, 21, "♋"], // Cancer
  [7, 23, "♌"], // Leo
  [8, 23, "♍"], // Virgo
  [9, 23, "♎"], // Libra
  [10, 23, "♏"], // Scorpio
  [11, 22, "♐"], // Sagittarius
  [12, 22, "♑"], // Capricorn
];

function currentZodiacGlyph(date) {
  const m = date.getUTCMonth() + 1;
  const d = date.getUTCDate();
  let active = ZODIAC_SIGNS[ZODIAC_SIGNS.length - 1][2];
  for (const [month, day, glyph] of ZODIAC_SIGNS) {
    if (m > month || (m === month && d >= day)) {
      active = glyph;
    } else {
      break;
    }
  }
  return active;
}

function eotCalendarYear(year) {
  const start = Date.UTC(year, 0, 1);
  const end = Date.UTC(year + 1, 0, 1);
  const out = [];
  let i = 0;
  for (let t = start; t < end; t += 86400000) {
    const d = new Date(t);
    out.push({ index: i, date: d, eotMinutes: equationOfTimeMinutes(d) });
    i += 1;
  }
  return out;
}

const AstroCore = {
  equationOfTimeMinutes,
  solarDeclinationRad,
  sunTimes,
  moonIllumination,
  moonPhaseName,
  currentZodiacGlyph,
  ZODIAC_SIGNS,
  eotCalendarYear,
  dayOfYearUTC,
};

// Scriptable's importModule() reads `module.exports`; plain Node also
// understands this via CommonJS. No effect when loaded via a <script> tag.
if (typeof module !== "undefined") {
  module.exports = AstroCore;
}
