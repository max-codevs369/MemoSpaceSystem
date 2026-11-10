from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from extensions import db
from services import identity_service as ids
from .helpers import identity_required

bp = Blueprint("onboarding", __name__)


@bp.get("/onboarding")
def start():
    if ids.current_user():
        return redirect(url_for("notes.index"))
    ids.get_onboarding_nonce()
    return render_template("onboarding.html")


@bp.post("/onboarding/validate")
def validate_step():
    data = request.get_json(silent=True) or {}
    step = data.get("step")
    if step == 1:
        _, err = ids.validate_name(data.get("name"))
        return jsonify(ok=err is None, errors={"name": err} if err else {})
    if step == 2:
        _, err = ids.validate_birth_date(data.get("birth_date"))
        return jsonify(ok=err is None, errors={"birth_date": err} if err else {})
    return jsonify(ok=False, errors={"_": "Langkah tidak dikenal."}), 400


@bp.post("/onboarding/complete")
def complete():
    if ids.current_user():
        return jsonify(ok=True, redirect=url_for("onboarding.welcome"))

    data = request.get_json(silent=True) or {}
    name, name_err = ids.validate_name(data.get("name"))
    birth, birth_err = ids.validate_birth_date(data.get("birth_date"))
    errors = {}
    if name_err:
        errors["name"] = name_err
    if birth_err:
        errors["birth_date"] = birth_err
    if errors:
        return jsonify(ok=False, errors=errors), 422

    ids.complete_onboarding(name, birth)
    return jsonify(ok=True, redirect=url_for("onboarding.welcome"))


@bp.get("/welcome")
@identity_required
def welcome(user):
    recovery_code = session.pop("new_recovery_code", None)
    return render_template("welcome.html", recovery_code=recovery_code)


@bp.post("/recover")
def recover():
    data = request.get_json(silent=True) or {}
    if ids.recovery_rate_limited(request.remote_addr or "unknown"):
        return jsonify(ok=False, error="Terlalu banyak percobaan. Coba lagi sebentar lagi."), 429
    user = ids.recover_with_code(data.get("code", ""))
    if user is None:
        return jsonify(ok=False, error="Kode pemulihan tidak valid."), 404
    return jsonify(ok=True, redirect=url_for("notes.index"))
