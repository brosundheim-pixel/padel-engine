"""Pull Census ACS 5-year demographics for zip codes in calibration anchors.

Reads zips from data/calibration/anchors.csv, queries Census ACS 2022 5-year
estimates per ZCTA, caches raw JSON to data/raw/census/{zip}.json, writes
demographic columns back into anchors.csv.

ACS variable map:
  B19013_001E  median household income
  B25077_001E  median home value
  B01002_001E  median age
  B01003_001E  total population
  B25003_001E  total occupied housing units
  B25003_002E  owner-occupied units
  B01001_011E..015E  male  age 25-29, 30-34, 35-39, 40-44, 45-49
  B01001_035E..039E  female age 25-29, 30-34, 35-39, 40-44, 45-49

Note: ACS bins age 50-54 as a single bucket. Computing exact 25-50 requires
splitting that bin. We use 25-49 (the clean ACS slice) and call the column
pct_age_25_49 to avoid implying false precision.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ACS_YEAR = 2023
ACS_BASE = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"

VARIABLES = [
    "B19013_001E",
    "B25077_001E",
    "B01002_001E",
    "B01003_001E",
    "B25003_001E",
    "B25003_002E",
    "B01001_011E",
    "B01001_012E",
    "B01001_013E",
    "B01001_014E",
    "B01001_015E",
    "B01001_035E",
    "B01001_036E",
    "B01001_037E",
    "B01001_038E",
    "B01001_039E",
]

AGE_25_49_VARS = [
    "B01001_011E",
    "B01001_012E",
    "B01001_013E",
    "B01001_014E",
    "B01001_015E",
    "B01001_035E",
    "B01001_036E",
    "B01001_037E",
    "B01001_038E",
    "B01001_039E",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
ANCHORS_CSV = REPO_ROOT / "data" / "calibration" / "anchors.csv"
RAW_DIR = REPO_ROOT / "data" / "raw" / "census"


class ACSResponse(BaseModel):
    """Parsed single-row ACS response for one ZCTA."""

    zip: str = Field(..., description="ZCTA5 code")
    median_household_income: Optional[int]
    median_home_value: Optional[int]
    median_age: Optional[float]
    total_population: Optional[int]
    occupied_housing_units: Optional[int]
    owner_occupied_units: Optional[int]
    age_25_49_count: Optional[int]

    @property
    def homeownership_rate(self) -> Optional[float]:
        if not self.occupied_housing_units or self.owner_occupied_units is None:
            return None
        return round(self.owner_occupied_units / self.occupied_housing_units, 4)

    @property
    def pct_age_25_49(self) -> Optional[float]:
        if not self.total_population or self.age_25_49_count is None:
            return None
        return round(self.age_25_49_count / self.total_population, 4)


def _coerce(value: Any) -> Optional[float]:
    """ACS uses negative sentinels (-666666666 etc.) for missing. Drop them."""
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return n


def fetch_zcta(zcta: str, api_key: str) -> Any:
    """Fetch raw Census ACS response for one ZCTA. Returns parsed JSON list."""
    params = {
        "get": ",".join(VARIABLES),
        "for": f"zip code tabulation area:{zcta}",
        "key": api_key,
    }
    resp = requests.get(ACS_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def cache_raw(zcta: str, payload: Any) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{zcta}.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def parse_response(zcta: str, payload: Any) -> ACSResponse:
    """ACS returns [[header...], [values...]]. Map by header."""
    if not payload or len(payload) < 2:
        raise ValueError(f"Empty Census response for {zcta}: {payload!r}")
    header, row = payload[0], payload[1]
    record = dict(zip(header, row))

    def gi(key: str) -> int | None:
        v = _coerce(record.get(key))
        return int(v) if v is not None else None

    def gf(key: str) -> float | None:
        return _coerce(record.get(key))

    age_vals = [gi(k) for k in AGE_25_49_VARS]
    age_total = sum(v for v in age_vals if v is not None) if any(v is not None for v in age_vals) else None

    return ACSResponse(
        zip=zcta,
        median_household_income=gi("B19013_001E"),
        median_home_value=gi("B25077_001E"),
        median_age=gf("B01002_001E"),
        total_population=gi("B01003_001E"),
        occupied_housing_units=gi("B25003_001E"),
        owner_occupied_units=gi("B25003_002E"),
        age_25_49_count=age_total,
    )


def load_anchors():
    with ANCHORS_CSV.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_anchors(fieldnames, rows):
    with ANCHORS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


NEW_COLUMNS = [
    "median_household_income",
    "median_home_value",
    "median_age",
    "total_population",
    "homeownership_rate",
    "pct_age_25_49",
]


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("CENSUS_API_KEY")
    if not api_key:
        print("ERROR: CENSUS_API_KEY missing from .env", file=sys.stderr)
        return 1

    fieldnames, rows = load_anchors()
    if not rows:
        print("ERROR: anchors.csv has no rows", file=sys.stderr)
        return 1

    out_fields = list(fieldnames)
    for col in NEW_COLUMNS:
        if col not in out_fields:
            out_fields.append(col)

    for row in rows:
        zcta = row["zip"].strip()
        print(f"Fetching ACS {ACS_YEAR} for ZCTA {zcta}...")
        payload = fetch_zcta(zcta, api_key)
        cache_raw(zcta, payload)
        parsed = parse_response(zcta, payload)

        row["median_household_income"] = (
            str(parsed.median_household_income) if parsed.median_household_income is not None else ""
        )
        row["median_home_value"] = (
            str(parsed.median_home_value) if parsed.median_home_value is not None else ""
        )
        row["median_age"] = str(parsed.median_age) if parsed.median_age is not None else ""
        row["total_population"] = (
            str(parsed.total_population) if parsed.total_population is not None else ""
        )
        row["homeownership_rate"] = (
            f"{parsed.homeownership_rate:.4f}" if parsed.homeownership_rate is not None else ""
        )
        row["pct_age_25_49"] = (
            f"{parsed.pct_age_25_49:.4f}" if parsed.pct_age_25_49 is not None else ""
        )

    write_anchors(out_fields, rows)
    print(f"Wrote {len(rows)} rows to {ANCHORS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
