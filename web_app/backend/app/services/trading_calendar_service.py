from datetime import date, timedelta


CALENDAR_NAME = "a_share_builtin_2024"

HOLIDAYS_2024 = {
    date(2024, 1, 1),
    *{date(2024, 2, day) for day in range(9, 18)},
    date(2024, 4, 4),
    date(2024, 4, 5),
    *{date(2024, 5, day) for day in range(1, 6)},
    date(2024, 6, 10),
    date(2024, 9, 16),
    date(2024, 9, 17),
    *{date(2024, 10, day) for day in range(1, 8)},
}


def is_a_share_trading_day(day: date) -> bool:
    if day.year != 2024:
        return day.weekday() < 5
    return day.weekday() < 5 and day not in HOLIDAYS_2024


def expected_a_share_trading_days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days = []
    current = start
    while current <= end:
        if is_a_share_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def missing_a_share_trading_days(previous_day: date, current_day: date) -> list[date]:
    if current_day <= previous_day:
        return []
    return expected_a_share_trading_days(previous_day + timedelta(days=1), current_day - timedelta(days=1))
