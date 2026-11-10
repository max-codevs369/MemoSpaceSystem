from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import current_app

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def now_local() -> datetime:

    tz = ZoneInfo(current_app.config["APP_TIMEZONE"])
    return datetime.now(tz).replace(tzinfo=None, microsecond=0)


def today_local() -> date:
    return now_local().date()


def fmt_date(value) -> str:
    if not value:
        return "-"
    return f"{value.day} {BULAN[value.month - 1]} {value.year}"


def fmt_date_short(value) -> str:
    if not value:
        return "-"
    return f"{value.day} {BULAN[value.month - 1][:3]} {value.year}"


def fmt_time(value) -> str:
    if not value:
        return "-"
    return value.strftime("%H.%M")


def fmt_full_today() -> str:
    today = today_local()
    return f"{HARI[today.weekday()]}, {fmt_date(today)}"
