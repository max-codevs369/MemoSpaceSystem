from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from extensions import db
from services import identity_service as ids, note_service as ns
from utils import fmt_date
from .helpers import identity_required

bp = Blueprint("profile", __name__, url_prefix="/profile")


@bp.route("", methods=["GET", "POST"])
@identity_required
def settings(user):
    errors = {}
    if request.method == "POST":
        name, name_err = ids.validate_name(request.form.get("name"))
        birth, birth_err = ids.validate_birth_date(request.form.get("birth_date"))
        if name_err:
            errors["name"] = name_err
        if birth_err:
            errors["birth_date"] = birth_err
        if not errors:
            user.name, user.birth_date = name, birth
            db.session.commit()
            flash("Profil diperbarui.", "success")
            return redirect(url_for("profile.settings"))
    return render_template(
        "profile.html", errors=errors, total_notes=ns.count_notes(user),
        member_since=fmt_date(user.created_at),
        recovery_code=session.pop("shown_recovery_code", None),
    )


@bp.post("/recovery")
@identity_required
def regenerate(user):
    session["shown_recovery_code"] = ids.regenerate_recovery_code(user)
    flash("Kode pemulihan baru dibuat. Kode lama tidak berlaku lagi.", "success")
    return redirect(url_for("profile.settings"))


@bp.post("/sign-out")
@identity_required
def sign_out(user):
    ids.sign_out()
    flash("Kamu keluar dari perangkat ini. Gunakan kode pemulihan untuk masuk kembali.", "info")
    return redirect(url_for("onboarding.start"))


@bp.post("/delete")
@identity_required
def delete_account(user):
    if (request.form.get("confirm") or "").strip().upper() != "HAPUS":
        flash("Ketik HAPUS untuk mengonfirmasi penghapusan akun.", "error")
        return redirect(url_for("profile.settings"))
    ids.delete_account(user)
    return redirect(url_for("onboarding.start"))
