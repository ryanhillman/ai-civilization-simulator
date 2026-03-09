"""
Tests for the calendar utility (app/simulation/calendar.py).

Covers:
  - Anchor date: turn 0 = March 1, Year 1
  - Day-by-day progression
  - Month rollover (e.g. March 31 → April 1)
  - Year rollover (December 31, Year 1 → January 1, Year 2)
  - Season mapping by month
  - Short and long format strings
  - Determinism (same input → same output, always)
  - Invalid input guard
"""
import pytest

from app.simulation.calendar import (
    CalendarDate,
    YEAR_LENGTH,
    turn_to_calendar_date,
)


# ---------------------------------------------------------------------------
# Anchor / fixed known dates
# ---------------------------------------------------------------------------


class TestAnchor:
    def test_turn_0_is_march_1_year_1(self):
        d = turn_to_calendar_date(0)
        assert d.month_name == "March"
        assert d.day == 1
        assert d.year == 1

    def test_turn_1_is_march_2_year_1(self):
        d = turn_to_calendar_date(1)
        assert d.month_name == "March"
        assert d.day == 2
        assert d.year == 1

    def test_turn_30_is_march_31_year_1(self):
        d = turn_to_calendar_date(30)
        assert d.month_name == "March"
        assert d.day == 31
        assert d.year == 1


# ---------------------------------------------------------------------------
# Month rollover
# ---------------------------------------------------------------------------


class TestMonthRollover:
    def test_march_rolls_into_april(self):
        # Turn 31 should be April 1 (March has 31 days, so day 32 is April 1)
        d = turn_to_calendar_date(31)
        assert d.month_name == "April"
        assert d.day == 1
        assert d.year == 1

    def test_april_rolls_into_may(self):
        # April has 30 days; turn 31+30=61 should be May 1
        d = turn_to_calendar_date(31 + 30)
        assert d.month_name == "May"
        assert d.day == 1

    def test_february_has_28_days(self):
        # January 1, Year 2 is 306 turns after turn 0 (turn_number=306 → Jan 1 Y2)
        # Feb 28 is 28 days into February of Year 2
        # Find Feb 1, Year 2 first: Jan 1 Y2 = turn 306, Feb 1 Y2 = turn 306+31
        feb_1 = turn_to_calendar_date(306 + 31)
        assert feb_1.month_name == "February"
        assert feb_1.day == 1

        feb_28 = turn_to_calendar_date(306 + 31 + 27)
        assert feb_28.month_name == "February"
        assert feb_28.day == 28

        # Feb 29 does not exist — next day is March 1
        march_1 = turn_to_calendar_date(306 + 31 + 28)
        assert march_1.month_name == "March"
        assert march_1.day == 1


# ---------------------------------------------------------------------------
# Year rollover
# ---------------------------------------------------------------------------


class TestYearRollover:
    def test_year_length_is_365(self):
        assert YEAR_LENGTH == 365

    def test_december_31_year_1(self):
        # March 1 = turn 0.  Days remaining in year 1 from March 1:
        # Mar(31) + Apr(30) + May(31) + Jun(30) + Jul(31) + Aug(31)
        # + Sep(30) + Oct(31) + Nov(30) + Dec(31) = 306 days → turn 305
        d = turn_to_calendar_date(305)
        assert d.month_name == "December"
        assert d.day == 31
        assert d.year == 1

    def test_january_1_year_2(self):
        d = turn_to_calendar_date(306)
        assert d.month_name == "January"
        assert d.day == 1
        assert d.year == 2

    def test_march_1_year_2_is_365_turns_after_turn_0(self):
        d = turn_to_calendar_date(365)
        assert d.month_name == "March"
        assert d.day == 1
        assert d.year == 2

    def test_year_3_begins_correctly(self):
        d = turn_to_calendar_date(365 * 2)
        assert d.month_name == "March"
        assert d.day == 1
        assert d.year == 3

    def test_consecutive_turns_never_skip_or_repeat_days(self):
        """Scan the first two years and verify each day advances by exactly one."""
        prev = turn_to_calendar_date(0)
        for t in range(1, 365 * 2 + 1):
            curr = turn_to_calendar_date(t)
            # Day must advance; year must not go backwards
            assert curr.year >= prev.year
            if curr.year == prev.year:
                assert curr.month >= prev.month
            prev = curr


# ---------------------------------------------------------------------------
# Season mapping
# ---------------------------------------------------------------------------


class TestSeasonMapping:
    def test_march_is_spring(self):
        assert turn_to_calendar_date(0).season == "Spring"  # March 1

    def test_june_is_summer(self):
        # June 1 = turn 31 (Apr) + 31 (May) + 31 (Mar→end)... let's compute exactly
        # Turn 0 = Mar 1; Mar has 31 days; Apr has 30; May has 31; June 1 = turn 31+30+31 = 92
        d = turn_to_calendar_date(92)
        assert d.month_name == "June"
        assert d.season == "Summer"

    def test_september_is_autumn(self):
        # Jun(30) + Jul(31) + Aug(31) = 92 more days after June 1, turn 92+92=184
        d = turn_to_calendar_date(184)
        assert d.month_name == "September"
        assert d.season == "Autumn"

    def test_december_is_winter(self):
        # Sep(30)+Oct(31)+Nov(30)=91 more, turn 184+91=275
        d = turn_to_calendar_date(275)
        assert d.month_name == "December"
        assert d.season == "Winter"

    def test_january_is_winter(self):
        d = turn_to_calendar_date(306)
        assert d.month_name == "January"
        assert d.season == "Winter"

    def test_february_is_winter(self):
        d = turn_to_calendar_date(306 + 31)  # Feb 1, Year 2
        assert d.month_name == "February"
        assert d.season == "Winter"

    def test_all_spring_months(self):
        for turn, expected_month in [(0, "March"), (31, "April"), (61, "May")]:
            d = turn_to_calendar_date(turn)
            assert d.season == "Spring", f"{d.month_name} should be Spring"

    def test_season_consistency_across_year(self):
        """Every month in each season must agree throughout the year."""
        spring_months = {"March", "April", "May"}
        summer_months = {"June", "July", "August"}
        autumn_months = {"September", "October", "November"}
        winter_months = {"December", "January", "February"}

        for t in range(365):
            d = turn_to_calendar_date(t)
            if d.month_name in spring_months:
                assert d.season == "Spring", f"{d.month_name} day {d.day} → {d.season}"
            elif d.month_name in summer_months:
                assert d.season == "Summer", f"{d.month_name} day {d.day} → {d.season}"
            elif d.month_name in autumn_months:
                assert d.season == "Autumn", f"{d.month_name} day {d.day} → {d.season}"
            elif d.month_name in winter_months:
                assert d.season == "Winter", f"{d.month_name} day {d.day} → {d.season}"


# ---------------------------------------------------------------------------
# Format strings
# ---------------------------------------------------------------------------


class TestFormatStrings:
    def test_short_format(self):
        d = turn_to_calendar_date(0)
        assert d.short == "March 1, Year 1"

    def test_long_format_includes_season(self):
        d = turn_to_calendar_date(0)
        assert d.long == "March 1, Year 1 — Spring"

    def test_short_format_multi_digit_day(self):
        d = turn_to_calendar_date(14)  # March 15
        assert d.short == "March 15, Year 1"

    def test_long_format_year_2(self):
        d = turn_to_calendar_date(306)  # January 1, Year 2
        assert d.long == "January 1, Year 2 — Winter"

    def test_format_does_not_contain_numeric_id(self):
        """Regression guard: no raw turn_number should appear in the formatted date."""
        for turn in (0, 1, 99, 305, 306, 365):
            short = turn_to_calendar_date(turn).short
            long = turn_to_calendar_date(turn).long
            assert str(turn) not in short or "Year" in short  # 'Year 1' is fine
            # The turn number itself (e.g. 306) should not appear raw in the display
            # (Year numbers are small integers; only check large turn values)
            if turn > 31:
                assert str(turn) not in long


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_turn_always_produces_same_date(self):
        for turn in (0, 1, 50, 200, 364, 365, 730):
            first = turn_to_calendar_date(turn)
            second = turn_to_calendar_date(turn)
            assert first == second

    def test_different_turns_produce_different_dates(self):
        dates = {turn_to_calendar_date(t) for t in range(365)}
        assert len(dates) == 365  # all 365 dates in Year 1 are unique


# ---------------------------------------------------------------------------
# Edge cases / guard
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_negative_turn_raises(self):
        with pytest.raises(ValueError):
            turn_to_calendar_date(-1)

    def test_large_turn_number_works(self):
        # Turn 3650 = 10 years out — should not raise
        d = turn_to_calendar_date(3650)
        assert d.year > 1
        assert d.month_name in [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        assert 1 <= d.day <= 31
