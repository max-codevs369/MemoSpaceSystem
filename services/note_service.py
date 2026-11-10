from datetime import datetime, timedelta

from flask import abort, current_app
from sqlalchemy import case, func, or_, select

from extensions import db
from models import Category, Note
from utils import now_local


def get_owned_note(user, note_id: int, include_deleted: bool = False) -> Note:
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user.id)
    if not include_deleted:
        stmt = stmt.where(Note.deleted_at.is_(None))
    note = db.session.execute(stmt).scalar_one_or_none()
    if note is None:
        abort(404)
    return note


def get_owned_trashed_note(user, note_id: int) -> Note:
    note = db.session.execute(
        select(Note).where(Note.id == note_id, Note.user_id == user.id, Note.deleted_at.is_not(None))
    ).scalar_one_or_none()
    if note is None:
        abort(404)
    return note


def get_owned_category(user, category_id: int) -> Category:
    cat = db.session.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user.id)
    ).scalar_one_or_none()
    if cat is None:
        abort(404)
    return cat


def list_categories(user):
    return db.session.execute(
        select(Category).where(Category.user_id == user.id).order_by(func.lower(Category.name))
    ).scalars().all()


def clean_note_input(user, title, content, category_id):
    """Kembalikan (data, errors). Semua input dianggap tidak tepercaya."""
    cfg = current_app.config
    errors = {}

    title = " ".join((title or "").split())
    content = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    content = content.replace("\x00", "")

    if not title:
        errors["title"] = "Judul wajib diisi."
    elif len(title) > cfg["NOTE_TITLE_MAX"]:
        errors["title"] = f"Judul maksimal {cfg['NOTE_TITLE_MAX']} karakter."
    if len(content) > cfg["NOTE_CONTENT_MAX"]:
        errors["content"] = f"Isi catatan maksimal {cfg['NOTE_CONTENT_MAX']:,} karakter.".replace(",", ".")

    cat_id = None
    if category_id not in (None, "", "0"):
        try:
            cat_id = int(category_id)
        except (TypeError, ValueError):
            errors["category_id"] = "Kategori tidak valid."
        else:
            owned = db.session.execute(
                select(Category.id).where(Category.id == cat_id, Category.user_id == user.id)
            ).scalar_one_or_none()
            if owned is None:
                errors["category_id"] = "Kategori tidak ditemukan."

    return {"title": title, "content": content, "category_id": cat_id}, errors


def create_note(user, data) -> Note:
    stamp = now_local()
    note = Note(
        user_id=user.id, title=data["title"], content=data["content"],
        category_id=data["category_id"], created_at=stamp, updated_at=stamp,
    )
    db.session.add(note)
    db.session.commit()
    return note


def update_note(note: Note, data) -> Note:
    note.title = data["title"]
    note.content = data["content"]
    note.category_id = data["category_id"]
    note.updated_at = now_local()
    db.session.commit()
    return note


def toggle_favorite(note: Note) -> bool:
    note.is_favorite = not note.is_favorite
    db.session.commit()
    return note.is_favorite


def soft_delete(note: Note) -> None:
    note.deleted_at = now_local()
    db.session.commit()


def restore(note: Note) -> None:
    note.deleted_at = None
    db.session.commit()


def purge(note: Note) -> None:
    db.session.delete(note)
    db.session.commit()


def empty_trash(user) -> int:
    count = Note.query.filter(Note.user_id == user.id, Note.deleted_at.is_not(None)).delete(
        synchronize_session=False
    )
    db.session.commit()
    return count


def purge_expired_trash(user) -> int:
    cutoff = now_local() - timedelta(days=current_app.config["TRASH_RETENTION_DAYS"])
    count = Note.query.filter(
        Note.user_id == user.id, Note.deleted_at.is_not(None), Note.deleted_at < cutoff
    ).delete(synchronize_session=False)
    if count:
        db.session.commit()
    return count


def trash_days_left(note: Note) -> int:
    expires = note.deleted_at + timedelta(days=current_app.config["TRASH_RETENTION_DAYS"])
    return max(0, (expires - now_local()).days + 1)


def create_category(user, name):
    name = " ".join((name or "").split())
    if not name:
        return None, "Nama kategori wajib diisi."
    if len(name) > 50:
        return None, "Nama kategori maksimal 50 karakter."
    exists = db.session.execute(
        select(Category.id).where(Category.user_id == user.id, func.lower(Category.name) == name.lower())
    ).first()
    if exists:
        return None, "Kategori dengan nama itu sudah ada."
    cat = Category(user_id=user.id, name=name)
    db.session.add(cat)
    db.session.commit()
    return cat, None


def _like_pattern(term: str) -> str:
    esc = term.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{esc}%"


def build_query(user, f, trashed: bool = False):
    stmt = select(Note).where(Note.user_id == user.id)
    stmt = stmt.where(Note.deleted_at.is_not(None) if trashed else Note.deleted_at.is_(None))

    terms = f.q.split()[:8] if f.q else []
    for term in terms:
        pattern = _like_pattern(term)
        stmt = stmt.where(
            or_(Note.title.ilike(pattern, escape="!"), Note.content.ilike(pattern, escape="!"))
        )

    if f.date:
        start = datetime.combine(f.date, datetime.min.time())
        stmt = stmt.where(Note.created_at >= start, Note.created_at < start + timedelta(days=1))
    else:
        if f.start:
            stmt = stmt.where(Note.created_at >= datetime.combine(f.start, datetime.min.time()))
        if f.end:
            stmt = stmt.where(
                Note.created_at < datetime.combine(f.end, datetime.min.time()) + timedelta(days=1)
            )

    if f.time_from or f.time_to:
        tcol = func.time(Note.created_at)
        lo = f"{f.time_from}:00" if f.time_from else "00:00:00"
        hi = f"{f.time_to}:59" if f.time_to else "23:59:59"
        if lo <= hi:
            stmt = stmt.where(tcol >= lo, tcol <= hi)
        else:
            stmt = stmt.where(or_(tcol >= lo, tcol <= hi))

    if f.category_id:
        stmt = stmt.where(Note.category_id == f.category_id)
    if f.favorite:
        stmt = stmt.where(Note.is_favorite.is_(True))

    if trashed:
        stmt = stmt.order_by(Note.deleted_at.desc())
    elif f.sort == "oldest":
        stmt = stmt.order_by(Note.created_at.asc(), Note.id.asc())
    elif f.sort == "title_asc":
        stmt = stmt.order_by(func.lower(Note.title).asc(), Note.id.asc())
    elif f.sort == "title_desc":
        stmt = stmt.order_by(func.lower(Note.title).desc(), Note.id.desc())
    else:
        if terms and not f.sort_explicit:
            title_hit = case((Note.title.ilike(_like_pattern(terms[0]), escape="!"), 0), else_=1)
            stmt = stmt.order_by(title_hit, Note.created_at.desc(), Note.id.desc())
        else:
            stmt = stmt.order_by(Note.created_at.desc(), Note.id.desc())
    return stmt


def count_notes(user) -> int:
    return db.session.scalar(
        select(func.count(Note.id)).where(Note.user_id == user.id, Note.deleted_at.is_(None))
    ) or 0


def count_trashed(user) -> int:
    return db.session.scalar(
        select(func.count(Note.id)).where(Note.user_id == user.id, Note.deleted_at.is_not(None))
    ) or 0


def snippet(text, length: int = 150) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= length else flat[:length].rstrip() + "…"
