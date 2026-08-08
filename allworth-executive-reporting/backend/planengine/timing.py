"""Resolve reusable timing expressions to calendar years."""

from __future__ import annotations

from .models import Timing, TimingKind


def resolve_timing(timing: Timing, ctx, *, start_year: int | None = None) -> int | None:
    kind = TimingKind(timing.kind)
    values = {
        TimingKind.NEVER: None,
        TimingKind.IMMEDIATELY: ctx.start_year,
        TimingKind.CALENDAR_YEAR: timing.value,
        TimingKind.CLIENT_AGE: ctx.client_birth_year + timing.value if timing.value is not None else None,
        TimingKind.SPOUSE_AGE: ctx.spouse_birth_year + timing.value if timing.value is not None else None,
        TimingKind.CLIENT_RETIREMENT: ctx.client_retirement_year,
        TimingKind.SPOUSE_RETIREMENT: ctx.spouse_retirement_year,
        TimingKind.CLIENT_DEATH: ctx.client_death_year,
        TimingKind.SPOUSE_DEATH: ctx.spouse_death_year,
        TimingKind.FIRST_DEATH: min(ctx.client_death_year, ctx.spouse_death_year),
        TimingKind.SECOND_DEATH: max(ctx.client_death_year, ctx.spouse_death_year),
    }
    if kind == TimingKind.DURATION_YEARS:
        if start_year is None:
            raise ValueError("duration_years requires a resolved start year")
        return start_year + int(timing.value or 0) - 1
    return values[kind]


def resolve_all(starts: Timing, ends: Timing, ctx) -> tuple[int | None, int | None]:
    start = resolve_timing(starts, ctx)
    end = resolve_timing(ends, ctx, start_year=start)
    if end is None:
        end = max(ctx.client_death_year, ctx.spouse_death_year)
    if start is not None and end < start:
        raise ValueError("end timing resolves before start timing")
    return start, end
