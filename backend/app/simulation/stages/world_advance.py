"""
Stage 1 — World Advance

Advances the in-world calendar: day, season, and weather.
No agent state is modified here.

Season cycle (120-day year):
  Days  1-30  → spring
  Days 31-60  → summer
  Days 61-90  → autumn
  Days 91-120 → winter

Weather is deterministic: derived from (day mod len(options)) so the same
turn always produces the same weather, making the engine reproducible.
"""
from app.enums import Season
from app.simulation.types import TurnContext

DAYS_PER_SEASON = 30
DAYS_PER_YEAR = 120

_SEASON_ORDER = [Season.spring, Season.summer, Season.autumn, Season.winter]

_WEATHER_BY_SEASON: dict[Season, list[str]] = {
    Season.spring: ["clear", "rainy", "cloudy", "mild"],
    Season.summer: ["sunny", "hot", "clear", "dry"],
    Season.autumn: ["cloudy", "windy", "foggy", "rainy"],
    Season.winter: ["cold", "snowy", "freezing", "overcast"],
}


def day_to_season(day: int) -> Season:
    """Return the season for a given in-world day (1-based, wraps each year)."""
    season_day = (day - 1) % DAYS_PER_YEAR
    index = season_day // DAYS_PER_SEASON
    return _SEASON_ORDER[index]


def advance_world(ctx: TurnContext) -> TurnContext:
    ws = ctx.world_state
    new_day = ws.current_day + 1
    new_season = day_to_season(new_day)
    weather_options = _WEATHER_BY_SEASON[new_season]
    new_weather = weather_options[new_day % len(weather_options)]

    updated = ws.model_copy(update={
        "current_day": new_day,
        "current_season": new_season,
        "weather": new_weather,
    })
    return ctx.model_copy(update={"world_state": updated})
