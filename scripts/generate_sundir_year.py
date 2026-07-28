#!/usr/bin/env python3
"""
Annual sun direction sampling script for heliostat surface optimization.

Core design principles:
1. Local solar time symmetry — sampling centered on local solar noon,
   ensuring morning/afternoon direction pairs are symmetric.
   (Paper uses wall-clock time, which is NOT symmetric at Delingha.)
2. 12-month sampling — paper shows date dimension saturates at 12 months.
3. Dense intraday sampling — ≥13 points per day, as paper shows intraday
   sampling is more sensitive than date sampling.
4. Configurable density — "paper" / "balanced" / "dense" presets for
   different accuracy-vs-speed trade-offs.

Reference:
  Ye & He (2026). Sensitivity Analysis of Time Sampling Points in Optical
  Efficiency Simulation of Heliostat Fields. CSA 16(3), 96-105.
  Conclusion: 12 days × 13 intraday points → <0.01% AFPA error vs GT.

Usage:
  # Default: balanced mode (12 months × 3 days × 13 intraday)
  python generate_sundir_year.py

  # Paper-recommended minimal set (~120 directions)
  python generate_sundir_year.py --mode paper

  # Dense set for final optimization (~650 directions)
  python generate_sundir_year.py --mode dense

  # Custom parameters
  python generate_sundir_year.py --months 12 --days-per-month 3 \
      --solar-start 6 --solar-end 18 --solar-step 1.0

  # With DNI weighting (outputs 4-column format)
  python generate_sundir_year.py --dni-weight --dni-model meinel

  # Custom location
  python generate_sundir_year.py --lat 37.36 --lon 97.29 --tz Asia/Shanghai

Output format:
  Each line: x y z [weight]
  - x, y, z: unit vector pointing TOWARD the sun (world coordinates)
  - weight: optional DNI weight (only with --dni-weight)
  - Comments (#) and empty lines are skipped by the loader.
"""

import argparse
import datetime
import math
import sys
from pathlib import Path

import numpy as np
import pytz
from pysolar.solar import get_altitude, get_azimuth


# ============================================================================
# DNI Models
# ============================================================================

def meinel_dni(altitude_deg: float) -> float:
    """
    Simplified Meinel atmospheric transparency model.
    AM = 1 / sin(altitude), DNI ∝ 0.7^(AM^0.678).

    Returns relative DNI weight [0, 1].
    """
    if altitude_deg <= 0:
        return 0.0
    h = math.radians(altitude_deg)
    am = 1.0 / (math.sin(h) + 1e-6)
    return 0.7 ** (am ** 0.678)


def mirval_dni(altitude_deg: float, site_altitude_km: float = 3.0) -> float:
    """
    MIRVAL / Sandia DNI model (Leary & Hankins, 1979).
    Used in the reference paper.

    DNI = G0 * (a + b * e^(-c / sin(ALT_solar)))
    with a, b, c depending on site altitude.

    Returns relative DNI weight [0, 1] (normalized to max possible).
    """
    if altitude_deg <= 0:
        return 0.0
    h = math.radians(altitude_deg)
    sinh = math.sin(h)

    alt = site_altitude_km  # site altitude in km
    a = 0.4237 - 0.00821 * (6.0 - alt) ** 2
    b = 0.5055 + 0.00595 * (6.5 - alt) ** 2
    c = 0.2711 + 0.01858 * (2.5 - alt) ** 2

    # Normalize: max DNI occurs at sin(h)=1 (zenith)
    dni = a + b * math.exp(-c / sinh)
    dni_max = a + b * math.exp(-c)  # at sin(h)=1
    return dni / dni_max if dni_max > 0 else 0.0


# ============================================================================
# Core sampling logic
# ============================================================================

def sun_direction_vector(altitude_deg: float, azimuth_deg: float):
    """
    Convert (altitude, azimuth) to a unit vector pointing TOWARD the sun.

    Azimuth convention (pysolar): 0=North, 90=East, 180=South, 270=West.
    Output convention:
      x = sin(A) * cos(h)   — east component
      y = sin(h)             — up component
      z = -cos(A) * cos(h)  — south component (positive z = southward)
    """
    h = math.radians(altitude_deg)
    A = math.radians(azimuth_deg)

    x = math.sin(A) * math.cos(h)
    y = math.sin(h)
    z = -math.cos(A) * math.cos(h)

    # Normalize (should already be unit, but ensure numerical stability)
    length = math.sqrt(x * x + y * y + z * z)
    if length > 0:
        x /= length
        y /= length
        z /= length

    return x, y, z


def find_true_solar_noon(
    lat: float,
    lon: float,
    tz,
    year: int,
    month: int,
    day: int,
    search_resolution_minutes: int = 1,
) -> datetime.datetime:
    """
    Find the true solar noon (sun crossing the local meridian) for a given day.

    For sites in the northern hemisphere with the sun to the south, true solar
    noon occurs when azimuth crosses 180° from E→S→W. We search for the time
    when azimuth is closest to 180° using a two-stage approach:
    1. Coarse scan at 10-minute resolution over the full day
    2. Fine scan at `search_resolution_minutes` around the best candidate.

    This ensures perfect geometric symmetry: sampling at ±Δt from true solar
    noon produces sun directions with identical altitude and opposite x-components.
    """
    # Coarse scan: check every 10 minutes from 10:00 to 16:00 local time
    best_dt = None
    best_err = 1e9

    for minute_of_day in range(10 * 60, 16 * 60 + 1, 10):
        hh, mm = minute_of_day // 60, minute_of_day % 60
        try:
            dt = tz.localize(datetime.datetime(year, month, day, hh, mm, 0))
        except Exception:
            continue
        az = get_azimuth(lat, lon, dt)
        err = abs(az - 180.0)
        if err < best_err:
            best_err = err
            best_dt = dt

    if best_dt is None:
        # Fallback: use mean solar noon
        utc_offset_hours = tz.utcoffset(datetime.datetime(year, 1, 1)).total_seconds() / 3600.0
        ref_meridian = utc_offset_hours * 15.0
        time_offset_minutes = (ref_meridian - lon) * 4.0
        wall_minutes = 12 * 60 + time_offset_minutes
        wall_hour = int(wall_minutes // 60) % 24
        wall_minute = int(wall_minutes % 60)
        return tz.localize(datetime.datetime(year, month, day, wall_hour, wall_minute, 0))

    # Fine scan around the best candidate
    refined_best_dt = best_dt
    refined_best_err = best_err
    for offset_min in range(-15, 16, search_resolution_minutes):
        candidate = best_dt + datetime.timedelta(minutes=offset_min)
        az = get_azimuth(lat, lon, candidate)
        err = abs(az - 180.0)
        if err < refined_best_err:
            refined_best_err = err
            refined_best_dt = candidate

    return refined_best_dt


def generate_sundirs(
    lat: float,
    lon: float,
    tz_name: str,
    year: int = 2023,
    months: list | None = None,
    days_of_month: list | None = None,
    solar_start: float = 6.0,
    solar_end: float = 18.0,
    solar_step: float = 1.0,
    min_altitude: float = 15.0,
    dni_model: str | None = None,
    site_altitude_km: float = 3.0,
    verbose: bool = False,
) -> np.ndarray:
    """
    Generate annual sun direction samples with TRUE solar-noon-symmetric sampling.

    For each calendar day, the true solar noon is computed (sun crossing the local
    meridian, azimuth ≈ 180°), and samples are taken at ±Δt offsets from this
    reference. This ensures perfect geometric symmetry: morning and afternoon
    sun directions at equal time offsets have identical altitude and opposite
    x-components (east-west), eliminating EoT-induced bias in the training set.

    This is a critical design choice for heliostat surface optimization: the
    mirror is physically symmetric, so the training distribution should be
    symmetric as well. The paper's wall-clock-time approach does not guarantee
    this — at Delingha (lon 97.29°E, tz UTC+8), 9:00 Beijing time corresponds
    to ~7:29 solar time while 15:00 is ~13:29, breaking symmetry.

    Parameters
    ----------
    lat, lon : float
        Site latitude and longitude (degrees).
    tz_name : str
        Timezone name (e.g., 'Asia/Shanghai').
    year : int
        Reference year for sun position calculation.
    months : list of int
        Months to sample (1-12). Default: all 12 months.
    days_of_month : list of int
        Days of month to sample. Default depends on mode.
    solar_start, solar_end : float
        Offset hours from true solar noon. solar_start < 0 = before noon,
        solar_end > 0 = after noon. Convention: 12.0 = noon for backward
        compatibility; internally converted to offsets: offset = hour - 12.
    solar_step : float
        Time step in hours.
    min_altitude : float
        Minimum solar altitude (degrees). Samples below this are discarded.
    dni_model : str or None
        DNI model: 'meinel', 'mirval', or None (no weighting).
    site_altitude_km : float
        Site altitude above sea level (km), for MIRVAL model.
    verbose : bool
        Print per-sample details.

    Returns
    -------
    np.ndarray of shape (N, 3) or (N, 4) if dni_model is not None.
    Columns: [x, y, z] or [x, y, z, weight].
    """
    if months is None:
        months = list(range(1, 13))

    tz = pytz.timezone(tz_name)

    # Convert the solar_start/end convention (12.0 = noon) to offsets
    # For backward compatibility: solar_start=6 means 6h before noon
    offsets_hours = []
    h = solar_start
    while h <= solar_end + 1e-9:
        offsets_hours.append(h - 12.0)  # negative before noon, positive after
        h += solar_step

    if verbose:
        utc_offset_hours = tz.utcoffset(datetime.datetime(year, 1, 1)).total_seconds() / 3600.0
        ref_meridian = utc_offset_hours * 15.0
        time_offset_minutes = (ref_meridian - lon) * 4.0
        print(f"Timezone: {tz_name} (UTC{utc_offset_hours:+.0f}h)")
        print(f"Reference meridian: {ref_meridian:.1f}°E, Site longitude: {lon:.2f}°E")
        print(f"Mean solar noon offset: {time_offset_minutes:+.1f} min")
        print(f"True solar noon: computed per-day from pysolar (azimuth=180°)")
        print(f"Offsets from true noon: {[f'{o:+.1f}h' for o in offsets_hours]}")
        print(f"Min altitude filter: {min_altitude}°")
        print()

    data = []
    skipped = 0
    total = 0
    noon_cache = {}  # cache true solar noon per (month, day)

    for month in months:
        for day in days_of_month:
            # Skip invalid dates (e.g., Feb 30)
            try:
                datetime.date(year, month, day)
            except ValueError:
                continue

            # Find or retrieve true solar noon for this day
            cache_key = (month, day)
            if cache_key not in noon_cache:
                noon_cache[cache_key] = find_true_solar_noon(
                    lat, lon, tz, year, month, day
                )
            noon_dt = noon_cache[cache_key]

            if verbose:
                noon_str = noon_dt.strftime("%H:%M")
                print(f"  --- {year}-{month:02d}-{day:02d}  true solar noon = {noon_str} ---")

            for offset_h in offsets_hours:
                dt = noon_dt + datetime.timedelta(hours=offset_h)
                total += 1

                altitude = get_altitude(lat, lon, dt)
                if altitude < min_altitude:
                    skipped += 1
                    continue

                azimuth = get_azimuth(lat, lon, dt)
                x, y, z = sun_direction_vector(altitude, azimuth)

                if dni_model:
                    if dni_model == "meinel":
                        w = meinel_dni(altitude)
                    elif dni_model == "mirval":
                        w = mirval_dni(altitude, site_altitude_km)
                    else:
                        raise ValueError(f"Unknown DNI model: {dni_model}")
                    data.append([x, y, z, w])
                else:
                    data.append([x, y, z])

                if verbose:
                    noon_str = noon_dt.strftime("%H:%M")
                    wall_str = dt.strftime("%H:%M")
                    ampm = "AM" if offset_h < 0 else ("PM" if offset_h > 0 else "NOON")
                    w_str = f" w={data[-1][3]:.4f}" if dni_model else ""
                    print(
                        f"  {year}-{month:02d}-{day:02d} {offset_h:+.1f}h ({ampm}) "
                        f"wall={wall_str}  alt={altitude:5.1f}°  az={azimuth:6.1f}°  "
                        f"dir=({x:+.4f}, {y:+.4f}, {z:+.4f}){w_str}"
                    )

    arr = np.array(data, dtype=np.float64)
    if verbose or len(data) > 0:
        n_dni = "(no DNI)" if not dni_model else f"with {dni_model} DNI"
        print(f"\nTotal attempted: {total}, passed filter: {len(arr)}, skipped: {skipped}")
        print(f"Output shape: {arr.shape} {n_dni}")

    return arr


# ============================================================================
# Preset modes
# ============================================================================

PRESETS = {
    "paper": dict(
        description="12 months × 1 day (15th) × 13 intraday (6–18h, 1h step) — ~120 directions",
        months=list(range(1, 13)),
        days_of_month=[15],
        solar_start=6.0,
        solar_end=18.0,
        solar_step=1.0,
    ),
    "balanced": dict(
        description="12 months × 3 days (5,15,25) × 13 intraday (6–18h, 1h step) — ~330 directions",
        months=list(range(1, 13)),
        days_of_month=[5, 15, 25],
        solar_start=6.0,
        solar_end=18.0,
        solar_step=1.0,
    ),
    "dense": dict(
        description="12 months × all even days × 13 intraday (6–18h, 1h step) — ~650 directions",
        months=list(range(1, 13)),
        days_of_month=list(range(2, 29, 2)),
        solar_start=6.0,
        solar_end=18.0,
        solar_step=1.0,
    ),
    "paper-fine": dict(
        description="12 months × 1 day (15th) × 25 intraday (6–18h, 0.5h step) — ~200 directions",
        months=list(range(1, 13)),
        days_of_month=[15],
        solar_start=6.0,
        solar_end=18.0,
        solar_step=0.5,
    ),
}


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate annual sun direction samples for heliostat optimization.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Preset modes:
  paper       — 12×1×13 (~120 dirs): fast iteration, matches paper recommendation
  balanced    — 12×3×13 (~330 dirs): recommended for daily optimization [default]
  dense       — 12×14×13 (~650 dirs): thorough coverage, final results
  paper-fine  — 12×1×25 (~200 dirs): paper month + denser intraday

Examples:
  %(prog)s                            # balanced mode (recommended)
  %(prog)s --mode paper               # minimal set
  %(prog)s --mode dense --dni-weight  # dense set with DNI weighting
  %(prog)s --dni-weight --dni-model mirval  # use MIRVAL DNI model
  %(prog)s --lat 39.0 --lon 94.0 --tz Asia/Urumqi  # custom location
        """,
    )

    # --- Mode / presets ---
    parser.add_argument(
        "--mode", choices=list(PRESETS.keys()), default="balanced",
        help="Sampling preset (default: balanced)",
    )

    # --- Location ---
    parser.add_argument("--lat", type=float, default=37.36,
                        help="Latitude in degrees (default: 37.36 = Delingha)")
    parser.add_argument("--lon", type=float, default=97.29,
                        help="Longitude in degrees (default: 97.29 = Delingha)")
    parser.add_argument("--tz", default="Asia/Shanghai",
                        help="Timezone name (default: Asia/Shanghai)")
    parser.add_argument("--site-altitude-km", type=float, default=3.0,
                        help="Site altitude above sea level in km (default: 3.0)")

    # --- Custom overrides (override preset values) ---
    parser.add_argument("--months", type=str, default=None,
                        help="Comma-separated months, e.g. '1,3,5,7,9,11'")
    parser.add_argument("--days-per-month", type=str, default=None,
                        help="Comma-separated days, e.g. '5,15,25'")
    parser.add_argument("--solar-start", type=float, default=None,
                        help="Local solar time start hour (default: 6.0)")
    parser.add_argument("--solar-end", type=float, default=None,
                        help="Local solar time end hour (default: 18.0)")
    parser.add_argument("--solar-step", type=float, default=None,
                        help="Local solar time step in hours (default: 1.0)")

    # --- Filters & weights ---
    parser.add_argument("--min-altitude", type=float, default=15.0,
                        help="Minimum solar altitude in degrees (default: 15)")
    parser.add_argument("--dni-weight", action="store_true",
                        help="Include DNI weight as 4th column")
    parser.add_argument("--dni-model", choices=["meinel", "mirval"], default="meinel",
                        help="DNI model (default: meinel)")

    # --- Output ---
    parser.add_argument("--year", type=int, default=2023,
                        help="Reference year for sun position (default: 2023)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output file path (default: auto-generated name)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print every sample direction")

    args = parser.parse_args()

    # --- Resolve parameters: preset first, then CLI overrides ---
    preset = PRESETS[args.mode]
    months = preset["months"]
    days_of_month = preset["days_of_month"]
    solar_start = preset["solar_start"]
    solar_end = preset["solar_end"]
    solar_step = preset["solar_step"]

    if args.months is not None:
        months = [int(x.strip()) for x in args.months.split(",")]
    if args.days_per_month is not None:
        days_of_month = [int(x.strip()) for x in args.days_per_month.split(",")]
    if args.solar_start is not None:
        solar_start = args.solar_start
    if args.solar_end is not None:
        solar_end = args.solar_end
    if args.solar_step is not None:
        solar_step = args.solar_step

    dni_model = args.dni_model if args.dni_weight else None

    # --- Generate ---
    print(f"=== Heliostat Sun Direction Generator ===")
    print(f"Mode: {args.mode} — {preset['description']}")
    print(f"Location: lat={args.lat}, lon={args.lon}, tz={args.tz}")
    print(f"DNI weighting: {dni_model or 'disabled'}")
    print()

    arr = generate_sundirs(
        lat=args.lat,
        lon=args.lon,
        tz_name=args.tz,
        year=args.year,
        months=months,
        days_of_month=days_of_month,
        solar_start=solar_start,
        solar_end=solar_end,
        solar_step=solar_step,
        min_altitude=args.min_altitude,
        dni_model=dni_model,
        site_altitude_km=args.site_altitude_km,
        verbose=args.verbose,
    )

    if len(arr) == 0:
        print("ERROR: No samples generated. Check parameters and altitude filter.", file=sys.stderr)
        sys.exit(1)

    # --- Auto-generate output filename ---
    if args.output:
        out_path = Path(args.output)
    else:
        dni_tag = f"_{dni_model}" if dni_model else ""
        out_path = Path(f"{len(arr)}_sundir_year{dni_tag}.txt")

    # --- Save ---
    header = (
        f"# Annual sun direction samples for heliostat optimization\n"
        f"# Generated by generate_sundir_year.py\n"
        f"# Mode: {args.mode} | Location: lat={args.lat} lon={args.lon} tz={args.tz}\n"
        f"# Months: {months} | Days per month: {days_of_month}\n"
        f"# Solar window: {solar_start:.1f}–{solar_end:.1f}h | Step: {solar_step:.1f}h\n"
        f"# Min altitude filter: {args.min_altitude}°\n"
        f"# DNI model: {dni_model or 'none'}\n"
        f"# Total: {len(arr)} directions\n"
        f"# Columns: x y z" + (" weight" if dni_model else "") + "\n"
    )

    fmt = "%.8f %.8f %.8f" + (" %.6f" if dni_model else "")
    np.savetxt(str(out_path), arr, fmt=fmt, header=header.rstrip(), comments="")

    print(f"Saved {len(arr)} sun directions to: {out_path}")
    if dni_model:
        print(f"Format: x y z weight (4 columns)")
        print(f"Weight range: [{arr[:, 3].min():.4f}, {arr[:, 3].max():.4f}]")
    else:
        print(f"Format: x y z (3 columns, compatible with existing pipeline)")

    # --- Quick stats ---
    if not args.verbose:
        alts = np.degrees(np.arcsin(np.clip(arr[:, 1], -1, 1)))
        print(f"\nAltitude stats: min={alts.min():.1f}°  median={np.median(alts):.1f}°  max={alts.max():.1f}°")
        print(f"Sample count per month (approx): {len(arr) // len(months)}")


if __name__ == "__main__":
    main()
