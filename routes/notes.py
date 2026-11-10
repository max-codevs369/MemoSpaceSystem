from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template, request,
                   url_for, current_app)

from extensions import db
from services import export_service, note_service as ns
from utils import fmt_full_today, now_local
from .filters import SORTS, parse_filters
from .helpers import identity_required, wants_json

bp = Blueprint("notes", __name__)


def _form_errors_response(errors, status=422):
    return jsonify(ok=False, errors=errors), status


@bp.get("/")
@identity_required
def index(user):
    f = parse_filters(request.args)
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    pagination = db.paginate(
        ns.build_query(user, f), page=page, per_page=current_app.config["NOTES_PER_PAGE"], error_out=False
    )
    ctx = dict(
        notes=pagination.items, pagination=pagination, f=f, sorts=SORTS,
        total_notes=ns.count_notes(user), trash_count=ns.count_trashed(user),
        categories=ns.list_categories(user),
        query_args={k: v for k, v in request.args.items() if k != "page" and v},
    )
    if request.headers.get("X-Requested-With") == "fetch":
        return render_template("_notes_results.html", **ctx)
    return render_template("index.html", today=fmt_full_today(), **ctx)


@bp.route("/notes/new", methods=["GET", "POST"])
@identity_required
def create(user):
    categories = ns.list_categories(user)
    if request.method == "POST":
        data, errors = ns.clean_note_input(
            user, request.form.get("title"), request.form.get("content"), request.form.get("category_id")
        )
        if errors:
            return render_template("add_note.html", form=data, errors=errors, categories=categories), 422
        note = ns.create_note(user, data)
        flash("Catatan berhasil disimpan.", "success")
        return redirect(url_for("notes.detail", note_id=note.id))
    return render_template("add_note.html", form={}, errors={}, categories=categories)


@bp.get("/notes/<int:note_id>")
@identity_required
def detail(user, note_id):
    note = ns.get_owned_note(user, note_id)
    return render_template("detail_note.html", note=note)


@bp.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
@identity_required
def edit(user, note_id):
    note = ns.get_owned_note(user, note_id)
    categories = ns.list_categories(user)
    if request.method == "POST":
        data, errors = ns.clean_note_input(
            user, request.form.get("title"), request.form.get("content"), request.form.get("category_id")
        )
        if errors:
            return render_template(
                "edit_note.html", note=note, form=data, errors=errors, categories=categories
            ), 422
        ns.update_note(note, data)
        flash("Perubahan berhasil disimpan.", "success")
        return redirect(url_for("notes.detail", note_id=note.id))
    form = {"title": note.title, "content": note.content or "", "category_id": note.category_id}
    return render_template("edit_note.html", note=note, form=form, errors={}, categories=categories)


@bp.post("/notes/<int:note_id>/autosave")
@identity_required
def autosave(user, note_id):
    note = ns.get_owned_note(user, note_id)
    payload = request.get_json(silent=True) or {}
    data, errors = ns.clean_note_input(
        user, payload.get("title"), payload.get("content"), payload.get("category_id")
    )
    if errors:
        return _form_errors_response(errors)
    ns.update_note(note, data)
    return jsonify(ok=True, saved_at=note.updated_at.strftime("%H.%M.%S"))


@bp.post("/notes/<int:note_id>/favorite")
@identity_required
def favorite(user, note_id):
    note = ns.get_owned_note(user, note_id)
    state = ns.toggle_favorite(note)
    if wants_json():
        return jsonify(ok=True, is_favorite=state)
    return redirect(request.referrer or url_for("notes.index"))


@bp.post("/notes/<int:note_id>/delete")
@identity_required
def delete(user, note_id):
    ns.soft_delete(ns.get_owned_note(user, note_id))
    flash("Catatan dipindahkan ke Baru Dihapus. Kamu bisa memulihkannya kapan saja.", "success")
    return redirect(url_for("notes.index"))


@bp.get("/trash")
@identity_required
def trash(user):
    ns.purge_expired_trash(user)
    f = parse_filters({})
    notes = db.session.execute(ns.build_query(user, f, trashed=True)).scalars().all()
    return render_template(
        "trash.html", notes=notes, days_left=ns.trash_days_left,
        retention=current_app.config["TRASH_RETENTION_DAYS"],
    )


@bp.post("/notes/<int:note_id>/restore")
@identity_required
def restore(user, note_id):
    ns.restore(ns.get_owned_trashed_note(user, note_id))
    flash("Catatan berhasil dipulihkan.", "success")
    return redirect(url_for("notes.trash"))


@bp.post("/notes/<int:note_id>/purge")
@identity_required
def purge(user, note_id):
    ns.purge(ns.get_owned_trashed_note(user, note_id))
    flash("Catatan dihapus permanen.", "success")
    return redirect(url_for("notes.trash"))


@bp.post("/trash/empty")
@identity_required
def empty_trash(user):
    count = ns.empty_trash(user)
    flash(f"{count} catatan dihapus permanen." if count else "Tidak ada catatan untuk dihapus.", "success")
    return redirect(url_for("notes.trash"))


def _download(notes, fmt, filename):
    if fmt not in export_service.FORMATS:
        abort(404)
    mimetype, ext = export_service.FORMATS[fmt]
    body = export_service.render(notes, fmt)
    return Response(
        body, mimetype=mimetype.split(";")[0],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.{ext}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@bp.get("/notes/<int:note_id>/export/<fmt>")
@identity_required
def export_one(user, note_id, fmt):
    note = ns.get_owned_note(user, note_id)
    return _download([note], fmt, export_service.safe_filename(note.title))


@bp.get("/export/all/<fmt>")
@identity_required
def export_all(user, fmt):
    f = parse_filters({})
    notes = db.session.execute(ns.build_query(user, f)).scalars().all()
    if not notes:
        flash("Belum ada catatan untuk diekspor.", "info")
        return redirect(url_for("notes.index"))
    return _download(notes, fmt, f"memospace_{now_local():%Y%m%d}")
