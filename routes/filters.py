import re
from dataclasses import dataclass
from datetime import date as Date, datetime

SORTS = {"newest": "Terbaru", "oldest": "Terlama", "title_asc": "Judul A-Z", "title_desc": "Judul Z-A"}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class NoteFilters:
    q: str = ""
    date: Date | None = None
    start: Date | None = None
    end: Date | None = None
    time_from: str = ""
    time_to: str = ""
    category_id: int | None = None
    favorite: bool = False
    sort: str = "newest"
    sort_explicit: bool = False

    @property
    def date_filter_count(self) -> int:
        n = 0
        if self.date or self.start or self.end:
            n += 1
        if self.time_from or self.time_to:
            n += 1
        return n

    @property
    def is_active(self) -> bool:
        return bool(self.q or self.date_filter_count or self.category_id or self.favorite)


def _date(raw):
    try:
        return datetime.strptime((raw or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _time(raw):
    raw = (raw or "").strip()
    return raw if _TIME_RE.match(raw) else ""


def parse_filters(args) -> NoteFilters:
    f = NoteFilters()
    f.q = " ".join((args.get("q") or "").split())[:200]
    f.date = _date(args.get("date"))
    f.start, f.end = _date(args.get("start")), _date(args.get("end"))
    if f.start and f.end and f.start > f.end:
        f.start, f.end = f.end, f.start
    f.time_from, f.time_to = _time(args.get("time_from")), _time(args.get("time_to"))
    try:
        f.category_id = int(args.get("category")) if args.get("category") else None
    except ValueError:
        f.category_id = None
    f.favorite = args.get("fav") in {"1", "true", "on"}
    sort = args.get("sort")
    if sort in SORTS:
        f.sort, f.sort_explicit = sort, True
    return f
