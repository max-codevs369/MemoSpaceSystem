import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import date, datetime, timedelta

from flask import current_app, g, session
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import AnonymousUser, IdentityToken
from utils import now_local, today_local

_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_name(raw) -> tuple[str, str | None]:
    name = _CONTROL_CHARS.sub("", raw or "")
    name = " ".join(name.split())
    if not name:
        return "", "Nama wajib diisi."
    if len(name) > current_app.config["NAME_MAX"]:
        return name, f"Nama maksimal {current_app.config['NAME_MAX']} karakter."
    return name, None


def validate_birth_date(raw) -> tuple[date | None, str | None]:
    raw = (raw or "").strip()
    if not raw:
        return None, None  
    try:
        value = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None, "Format tanggal lahir tidak valid."
    if value > today_local():
        return None, "Tanggal lahir tidak boleh di masa depan."
    if value.year < 1900:
        return None, "Tanggal lahir tidak valid."
    return value, None


def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _normalize_recovery_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def _hash_recovery_code(code: str) -> str:
    return _sha256(_normalize_recovery_code(code))


def regenerate_recovery_code(user: AnonymousUser) -> str:
    code = _new_recovery_code()
    user.recovery_code_hash = _hash_recovery_code(code)
    db.session.commit()
    return code


def get_onboarding_nonce() -> str:
    nonce = session.get("onboard_nonce")
    if not nonce:
        nonce = secrets.token_hex(16)
        session["onboard_nonce"] = nonce
    return nonce


def complete_onboarding(name: str, birth_date: date | None) -> tuple[AnonymousUser, str]:
    nonce = get_onboarding_nonce()

    user = AnonymousUser.query.filter_by(onboarding_nonce=nonce).first()
    if user is None:
        user = AnonymousUser(
            anonymous_id=str(uuid.uuid4()), name=name, birth_date=birth_date, onboarding_nonce=nonce
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError: 
            db.session.rollback()
            user = AnonymousUser.query.filter_by(onboarding_nonce=nonce).first()
            if user is None:
                raise

    recovery_code = regenerate_recovery_code(user)
    sign_in(user)
    session["new_recovery_code"] = recovery_code
    return user, recovery_code


def sign_in(user: AnonymousUser) -> None:
    raw_token = secrets.token_urlsafe(32)
    db.session.add(IdentityToken(user_id=user.id, token_hash=_sha256(raw_token)))
    db.session.commit()
    session["uid"] = user.anonymous_id
    session["tok"] = raw_token
    session.permanent = True
    g.pop("current_user", None)


def sign_out() -> None:
    raw = session.get("tok")
    if raw:
        IdentityToken.query.filter_by(token_hash=_sha256(raw)).delete()
        db.session.commit()
    session.pop("uid", None)
    session.pop("tok", None)
    g.pop("current_user", None)


def current_user() -> AnonymousUser | None:
    if "current_user" in g:
        return g.current_user

    user = None
    uid, raw = session.get("uid"), session.get("tok")
    if uid and raw:
        token = (
            IdentityToken.query.filter_by(token_hash=_sha256(raw))
            .join(AnonymousUser, IdentityToken.user_id == AnonymousUser.id)
            .filter(AnonymousUser.anonymous_id == uid)
            .first()
        )
        if token is not None:
            user = token.owner
            if now_local() - token.last_seen_at > timedelta(hours=1):
                token.last_seen_at = now_local()
                db.session.commit()
        else:
            session.pop("uid", None)
            session.pop("tok", None)

    g.current_user = user
    return user


_attempts: dict[str, list[float]] = {}


def recovery_rate_limited(key: str, limit: int = 5, window: int = 60) -> bool:
    now = time.monotonic()
    hits = [t for t in _attempts.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _attempts[key] = hits
        return True
    hits.append(now)
    _attempts[key] = hits
    return False


def recover_with_code(code: str) -> AnonymousUser | None:
    normalized = _normalize_recovery_code(code)
    if len(normalized) != 16:
        return None
    digest = _sha256(normalized)
    user = AnonymousUser.query.filter_by(recovery_code_hash=digest).first()
    if user is None or not hmac.compare_digest(user.recovery_code_hash, digest):
        return None
    sign_in(user)
    return user


def delete_account(user: AnonymousUser) -> None:
    db.session.delete(user)  
    db.session.commit()
    session.clear()
    g.pop("current_user", None)
