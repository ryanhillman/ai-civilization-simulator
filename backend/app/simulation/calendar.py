"""
Calendar utility — maps turn_number to a human-readable date.

Anchor: Turn 0 = March 1, Year 1.
1 turn = 1 day.  No leap years.  365-day year.

Season is derived from the calendar month and follows the real-world
meteorological convention:
  Spring  — March, April, May
  Summer  — June, July, August
  Autumn  — September, October, November
  Winter  — December, January, February

This is intentionally independent of the simulation engine's internal
120-day season cycle, which drives game mechanics.  This module is
purely a presentation / date-mapping layer.
"""
from __future__ import annotations

from dataclasses import dataclass

_MONTH_NAMES: list[str] = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_MONTH_LENGTHS: list[int] = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

_MONTH_SEASON: list[str] = [
    "Winter",  # January
    "Winter",  # February
    "Spring",  # March
    "Spring",  # April
    "Spring",  # May
    "Summer",  # June
    "Summer",  # July
    "Summer",  # August
    "Autumn",  # September
    "Autumn",  # October
    "Autumn",  # November
    "Winter",  # December
]

YEAR_LENGTH: int = sum(_MONTH_LENGTHS)  # 365

# Days elapsed from January 1 to the anchor date (March 1), 0-indexed.
# January = 31 days, February = 28 days → March 1 is day index 59.
_ANCHOR_DAY_OF_YEAR: int = _MONTH_LENGTHS[0] + _MONTH_LENGTHS[1]  # 59


@dataclass(frozen=True)
class CalendarDate:
    month: int  # 0-indexed (0 = January … 11 = December)
    day: int    # 1-indexed day within the month (1…month_length)
    year: int   # 1-indexed year (1, 2, 3 …)

    @property
    def month_name(self) -> str:
        return _MONTH_NAMES[self.month]

    @property
    def season(self) -> str:
        return _MONTH_SEASON[self.month]

    @property
    def short(self) -> str:
        """e.g. 'March 1, Year 1'"""
        return f"{self.month_name} {self.day}, Year {self.year}"

    @property
    def long(self) -> str:
        """e.g. 'March 1, Year 1 — Spring'"""
        return f"{self.month_name} {self.day}, Year {self.year} — {self.season}"


def turn_to_calendar_date(turn_number: int) -> CalendarDate:
    """
    Convert a zero-indexed turn number to a CalendarDate.

    Turn 0 → March 1, Year 1.
    Turn 1 → March 2, Year 1.
    …and so on, one day per turn, wrapping across months and years.
    """
    if turn_number < 0:
        raise ValueError(f"turn_number must be >= 0, got {turn_number}")

    # Absolute day offset from January 1, Year 1 (0-indexed).
    total = _ANCHOR_DAY_OF_YEAR + turn_number

    year = total // YEAR_LENGTH + 1
    day_of_year = total % YEAR_LENGTH  # 0-indexed position within the year

    remaining = day_of_year
    for month_idx, length in enumerate(_MONTH_LENGTHS):
        if remaining < length:
            return CalendarDate(month=month_idx, day=remaining + 1, year=year)
        remaining -= length

    # Unreachable with a correct YEAR_LENGTH, but makes the type-checker happy.
    raise ValueError(f"Calendar computation failed for turn_number={turn_number}")
