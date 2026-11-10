from functools import wraps

from flask import jsonify, redirect, request, url_for

from services import identity_service


def identity_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = identity_service.current_user()
        if user is None:
            if request.is_json or request.headers.get("X-Requested-With") == "fetch":
                return jsonify(error="Sesi tidak ditemukan. Muat ulang halaman."), 401
            return redirect(url_for("onboarding.start"))
        return view(user, *args, **kwargs)
    return wrapped


def wants_json() -> bool:
    return request.is_json or request.headers.get("X-Requested-With") == "fetch"
