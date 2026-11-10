from flask import Blueprint, flash, jsonify, redirect, request, url_for

from extensions import db
from services import note_service as ns
from .helpers import identity_required, wants_json

bp = Blueprint("categories", __name__, url_prefix="/categories")


@bp.post("")
@identity_required
def create(user):
    name = request.form.get("name") or (request.get_json(silent=True) or {}).get("name")
    cat, err = ns.create_category(user, name)
    if wants_json():
        if err:
            return jsonify(ok=False, error=err), 422
        return jsonify(ok=True, id=cat.id, name=cat.name)
    flash(err or f"Kategori “{cat.name}” dibuat.", "error" if err else "success")
    return redirect(request.referrer or url_for("notes.index"))


@bp.post("/<int:category_id>/delete")
@identity_required
def delete(user, category_id):
    cat = ns.get_owned_category(user, category_id)
    name = cat.name
    db.session.delete(cat)  
    db.session.commit()
    flash(f"Kategori “{name}” dihapus. Catatan di dalamnya tetap aman.", "success")
    return redirect(url_for("notes.index"))
