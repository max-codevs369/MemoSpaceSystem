import re
from datetime import datetime

import pytest

from extensions import db
from models import AnonymousUser, Category, IdentityToken, Note


# ------------------------------------------------------------------ helpers
def csrf_of(client, path=None):
    """Ambil token CSRF dari meta tag. Pengguna anonim -> /onboarding, pengguna aktif -> /profile."""
    for candidate in ([path] if path else ["/onboarding", "/profile"]):
        html = client.get(candidate).get_data(as_text=True)
        m = re.search(r'name="csrf-token" content="([^"]+)"', html)
        if m:
            return m.group(1)
    raise AssertionError("token CSRF tidak ditemukan")


def onboard(client, name="Ghani", birth=""):
    token = csrf_of(client)
    res = client.post(
        "/onboarding/complete", json={"name": name, "birth_date": birth},
        headers={"X-CSRFToken": token},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    return res


def post(client, url, data=None, page="/"):
    token = csrf_of(client, page)
    return client.post(url, data={**(data or {}), "csrf_token": token})


def make_user(client, name="Ghani"):
    onboard(client, name)
    return AnonymousUser.query.filter_by(name=name).order_by(AnonymousUser.id.desc()).first()


def add_note(client, title="Judul", content="Isi", **extra):
    res = post(client, "/notes/new", {"title": title, "content": content, **extra}, page="/notes/new")
    assert res.status_code == 302, res.get_data(as_text=True)
    return Note.query.order_by(Note.id.desc()).first()


# ------------------------------------------------------------------ onboarding & identitas
def test_new_visitor_is_sent_to_onboarding(client):
    res = client.get("/")
    assert res.status_code == 302 and res.headers["Location"].endswith("/onboarding")


def test_onboarding_page_has_all_frames_and_no_login_fields(client):
    html = client.get("/onboarding").get_data(as_text=True)
    assert "Siapa nama kamu?" in html and "Kapan kamu lahir?" in html
    assert 'type="password"' not in html and 'type="email"' not in html


def test_onboarding_validation(client):
    token = csrf_of(client)
    h = {"X-CSRFToken": token}
    assert client.post("/onboarding/complete", json={"name": "   "}, headers=h).status_code == 422
    r = client.post("/onboarding/complete", json={"name": "A", "birth_date": "2999-01-01"}, headers=h)
    assert r.status_code == 422 and "birth_date" in r.get_json()["errors"]
    r = client.post("/onboarding/complete", json={"name": "A", "birth_date": "bukan-tanggal"}, headers=h)
    assert r.status_code == 422
    assert AnonymousUser.query.count() == 0


def test_onboarding_creates_user_with_uuid_and_httponly_cookie(client):
    res = onboard(client, "Ani", "2000-05-17")
    user = AnonymousUser.query.one()
    assert re.fullmatch(r"[0-9a-f-]{36}", user.anonymous_id)
    assert str(user.birth_date) == "2000-05-17"
    cookie = [c for c in res.headers.getlist("Set-Cookie") if c.startswith("memospace_session")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert user.anonymous_id not in cookie  # UUID mentah tidak bocor di cookie yang terbaca
    assert IdentityToken.query.count() == 1
    assert client.get("/").status_code == 200


def test_birth_date_is_optional(client):
    onboard(client, "Tanpa Tanggal")
    assert AnonymousUser.query.one().birth_date is None


def test_double_submit_does_not_create_duplicate_identity(client):
    token = csrf_of(client)
    h = {"X-CSRFToken": token}
    # Dua request dengan sesi yang sama (nonce sama), sebelum cookie baru diproses.
    with client.session_transaction() as s:
        before = dict(s)
    client.post("/onboarding/complete", json={"name": "Dobel"}, headers=h)
    with client.session_transaction() as s:
        s.pop("uid", None); s.pop("tok", None)
        s["onboard_nonce"] = before["onboard_nonce"]
    client.post("/onboarding/complete", json={"name": "Dobel"}, headers=h)
    assert AnonymousUser.query.count() == 1


def test_welcome_shows_recovery_code_once(client):
    onboard(client, "Budi")
    first = client.get("/welcome").get_data(as_text=True)
    assert "Selamat Datang di MemoSpace!" in first and "Budi" in first
    assert re.search(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", first)
    second = client.get("/welcome").get_data(as_text=True)
    assert not re.search(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", second)


def test_existing_user_skips_onboarding(client):
    onboard(client)
    assert client.get("/onboarding").status_code == 302


def test_revoked_token_loses_access(client):
    onboard(client)
    IdentityToken.query.delete(); db.session.commit()
    assert client.get("/").status_code == 302


def test_recovery_code_restores_access_on_new_browser(app, client):
    onboard(client, "Citra")
    code = re.search(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", client.get("/welcome").get_data(as_text=True)).group(0)
    add_note(client, "Rahasia", "isi rahasia")

    other = app.test_client()
    token = csrf_of(other)
    bad = other.post("/recover", json={"code": "AAAA-BBBB-CCCC-DDDD"}, headers={"X-CSRFToken": token})
    assert bad.status_code == 404
    good = other.post("/recover", json={"code": code.lower()}, headers={"X-CSRFToken": token})
    assert good.status_code == 200
    assert "Rahasia" in other.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ CSRF
def test_state_changing_requests_require_csrf(client):
    make_user(client)
    note = add_note(client)
    assert client.post(f"/notes/{note.id}/delete").status_code == 400
    assert client.post(f"/notes/{note.id}/favorite").status_code == 400
    assert client.post("/notes/new", data={"title": "x"}).status_code == 400
    assert client.post("/profile/delete", data={"confirm": "HAPUS"}).status_code == 400
    assert Note.query.count() == 1 and Note.query.one().deleted_at is None


def test_mutations_reject_get(client):
    make_user(client)
    note = add_note(client)
    assert client.get(f"/notes/{note.id}/delete").status_code == 405
    assert client.get(f"/notes/{note.id}/favorite").status_code == 405


# ------------------------------------------------------------------ CRUD
def test_pages_render(client):
    make_user(client)
    note = add_note(client)
    for url in ["/", "/notes/new", f"/notes/{note.id}", f"/notes/{note.id}/edit", "/trash", "/profile"]:
        assert client.get(url).status_code == 200, url


def test_empty_state(client):
    make_user(client)
    html = client.get("/").get_data(as_text=True)
    assert "Belum ada catatan. Yuk, buat catatan pertamamu!" in html and "Buat Catatan" in html


def test_create_requires_title_but_content_optional(client):
    make_user(client)
    res = post(client, "/notes/new", {"title": "  ", "content": "x"}, page="/notes/new")
    assert res.status_code == 422 and "Judul wajib diisi." in res.get_data(as_text=True)
    assert Note.query.count() == 0
    add_note(client, "Hanya judul", "")
    assert Note.query.count() == 1


def test_create_sets_server_time_and_owner(client):
    user = make_user(client)
    note = add_note(client, "Baru", "isi")
    assert note.user_id == user.id
    assert note.created_at == note.updated_at
    assert abs((datetime.now() - note.created_at).total_seconds()) < 24 * 3600 + 3600 * 14


def test_edit_keeps_created_at_and_changes_updated_at(client):
    make_user(client)
    note = add_note(client, "Lama", "isi")
    note.created_at = note.updated_at = datetime(2024, 1, 1, 8, 0, 0)
    db.session.commit()
    res = post(client, f"/notes/{note.id}/edit", {"title": "Baru", "content": "isi baru"}, page=f"/notes/{note.id}/edit")
    assert res.status_code == 302
    db.session.refresh(note)
    assert note.title == "Baru" and note.content == "isi baru"
    assert note.created_at == datetime(2024, 1, 1, 8, 0, 0)
    assert note.updated_at > note.created_at


def test_autosave_updates_note(client):
    make_user(client)
    note = add_note(client, "A", "b")
    token = csrf_of(client, f"/notes/{note.id}/edit")
    res = client.post(f"/notes/{note.id}/autosave", json={"title": "A2", "content": "b2"}, headers={"X-CSRFToken": token})
    assert res.status_code == 200 and res.get_json()["ok"]
    db.session.refresh(note)
    assert (note.title, note.content) == ("A2", "b2")
    bad = client.post(f"/notes/{note.id}/autosave", json={"title": "", "content": "x"}, headers={"X-CSRFToken": token})
    assert bad.status_code == 422


def test_xss_is_escaped(client):
    make_user(client)
    note = add_note(client, "<script>alert(1)</script>", "<img src=x onerror=alert(2)>")
    for url in ["/", f"/notes/{note.id}", f"/notes/{note.id}/edit"]:
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)" not in html and "<img src=x" not in html


def test_delete_trash_restore_purge(client):
    make_user(client)
    note = add_note(client, "Hapus aku", "x")
    post(client, f"/notes/{note.id}/delete")
    db.session.refresh(note)
    assert note.deleted_at is not None
    assert "Hapus aku" not in client.get("/").get_data(as_text=True)
    assert client.get(f"/notes/{note.id}").status_code == 404
    assert "Hapus aku" in client.get("/trash").get_data(as_text=True)

    post(client, f"/notes/{note.id}/restore", page="/trash")
    db.session.refresh(note)
    assert note.deleted_at is None
    post(client, f"/notes/{note.id}/delete")
    post(client, f"/notes/{note.id}/purge", page="/trash")
    assert Note.query.count() == 0


def test_expired_trash_is_purged(client, app):
    user = make_user(client)
    note = add_note(client, "Kadaluarsa", "x")
    post(client, f"/notes/{note.id}/delete")
    note.deleted_at = datetime(2020, 1, 1)
    db.session.commit()
    client.get("/trash")
    assert Note.query.count() == 0


def test_empty_trash(client):
    make_user(client)
    for t in ("a", "b"):
        n = add_note(client, t)
        post(client, f"/notes/{n.id}/delete")
    post(client, "/trash/empty", page="/trash")
    assert Note.query.count() == 0


# ------------------------------------------------------------------ isolasi data / IDOR
def test_users_cannot_touch_each_others_notes(app):
    a, b = app.test_client(), app.test_client()
    make_user(a, "Alice")
    secret = add_note(a, "Rahasia Alice", "isi pribadi")
    make_user(b, "Bob")
    nid = secret.id

    for method, url in [
        ("get", f"/notes/{nid}"), ("get", f"/notes/{nid}/edit"),
        ("get", f"/notes/{nid}/export/txt"), ("get", f"/notes/{nid}/export/pdf"),
    ]:
        assert getattr(b, method)(url).status_code == 404, url
    for url, kw in [
        (f"/notes/{nid}/delete", {}), (f"/notes/{nid}/favorite", {}),
        (f"/notes/{nid}/edit", {"data": {"title": "diretas"}}),
    ]:
        token = csrf_of(b)
        resp = b.post(url, data={"csrf_token": token, **kw.get("data", {})})
        assert resp.status_code == 404, url
    token = csrf_of(b)
    assert b.post(f"/notes/{nid}/autosave", json={"title": "x", "content": "y"}, headers={"X-CSRFToken": token}).status_code == 404
    assert b.post(f"/notes/{nid}/restore", data={"csrf_token": token}).status_code == 404

    assert "Rahasia Alice" not in b.get("/").get_data(as_text=True)
    assert "Rahasia Alice" not in b.get("/?q=Rahasia").get_data(as_text=True)
    assert "Rahasia Alice" not in b.get("/export/all/txt").get_data(as_text=True) or b.get("/export/all/txt").status_code == 302
    db.session.refresh(secret)
    assert secret.title == "Rahasia Alice" and secret.deleted_at is None and not secret.is_favorite


def test_cannot_use_other_users_category_or_inject_user_id(app):
    a, b = app.test_client(), app.test_client()
    make_user(a, "Alice")
    post(a, "/categories", {"name": "Pribadi"})
    cat = Category.query.one()
    bob = make_user(b, "Bob")
    res = post(b, "/notes/new", {"title": "x", "content": "y", "category_id": cat.id, "user_id": 1}, page="/notes/new")
    assert res.status_code == 422
    ok = add_note(b, "ok", "ok")
    assert ok.user_id == bob.id  # user_id dari form diabaikan
    assert post(b, f"/categories/{cat.id}/delete").status_code == 404


def test_forged_cookie_is_rejected(app):
    a = app.test_client()
    user = make_user(a, "Alice")
    attacker = app.test_client()
    with attacker.session_transaction() as s:  # penyerang tahu UUID tetapi tidak punya token
        s["uid"] = user.anonymous_id
        s["tok"] = "tebakan"
    assert attacker.get("/").status_code == 302


# ------------------------------------------------------------------ pencarian, filter, urutan
def seed(client):
    make_user(client)
    rows = [
        ("Belanja Mingguan", "susu, telur, roti", datetime(2026, 3, 1, 9, 15), True),
        ("Ide Proyek", "Aplikasi CATATAN dengan Flask", datetime(2026, 3, 5, 14, 30), False),
        ("Resep Nasi", "diskon 50% bumbu_dapur", datetime(2026, 3, 5, 23, 45), False),
        ("Zebra", "hewan belang", datetime(2026, 4, 20, 0, 5), False),
    ]
    for title, content, ts, fav in rows:
        n = add_note(client, title, content)
        n.created_at = n.updated_at = ts
        n.is_favorite = fav
    db.session.commit()


def titles(client, qs=""):
    html = client.get("/?" + qs, headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    return re.findall(r'class="ms-card-title"><a [^>]*>([^<]+)</a>', html)


def test_search_title_and_content_case_insensitive(client):
    seed(client)
    assert titles(client, "q=belanja") == ["Belanja Mingguan"]
    assert titles(client, "q=catatan") == ["Ide Proyek"]
    assert titles(client, "q=FLASK") == ["Ide Proyek"]
    assert titles(client, "q=flask aplikasi") == ["Ide Proyek"]  # semua kata harus cocok
    assert titles(client, "q=tidakada") == []
    assert "Tidak ada catatan yang cocok" in client.get("/?q=tidakada").get_data(as_text=True)


def test_search_wildcards_are_literal(client):
    seed(client)
    assert titles(client, "q=%25") == ["Resep Nasi"]      # '%' harfiah
    assert titles(client, "q=_") == ["Resep Nasi"]        # '_' harfiah
    assert titles(client, "q=%27 OR 1=1 --") == []        # tidak bisa SQL injection


def test_date_filters(client):
    seed(client)
    assert sorted(titles(client, "date=2026-03-05")) == ["Ide Proyek", "Resep Nasi"]
    assert sorted(titles(client, "start=2026-03-01&end=2026-03-05")) == ["Belanja Mingguan", "Ide Proyek", "Resep Nasi"]
    assert titles(client, "start=2026-04-01") == ["Zebra"]
    assert sorted(titles(client, "start=2026-03-05&end=2026-03-01")) == sorted(titles(client, "start=2026-03-01&end=2026-03-05"))
    assert titles(client, "date=2026-03-06") == []
    # Tepi hari tidak bergeser: 23:45 tetap 5 Maret, 00:05 tetap 20 April
    assert titles(client, "date=2026-04-20") == ["Zebra"]
    assert titles(client, "date=ngawur") != []  # tanggal rusak diabaikan, bukan galat


def test_time_filters(client):
    seed(client)
    assert titles(client, "time_from=09:00&time_to=10:00") == ["Belanja Mingguan"]
    assert titles(client, "time_from=14:30&time_to=14:30") == ["Ide Proyek"]
    assert titles(client, "time_from=23:00") == ["Resep Nasi"]
    assert sorted(titles(client, "time_from=23:00&time_to=01:00")) == ["Resep Nasi", "Zebra"]  # lewat tengah malam
    assert titles(client, "date=2026-03-05&time_from=20:00") == ["Resep Nasi"]  # gabungan tanggal + jam
    assert titles(client, "q=nasi&date=2026-03-05") == ["Resep Nasi"]  # gabungan pencarian + filter


def test_sorting_and_favorites(client):
    seed(client)
    assert titles(client) == ["Zebra", "Resep Nasi", "Ide Proyek", "Belanja Mingguan"]
    assert titles(client, "sort=oldest")[0] == "Belanja Mingguan"
    assert titles(client, "sort=title_asc") == ["Belanja Mingguan", "Ide Proyek", "Resep Nasi", "Zebra"]
    assert titles(client, "sort=title_desc")[0] == "Zebra"
    assert titles(client, "fav=1") == ["Belanja Mingguan"]


def test_favorite_toggle_endpoint(client):
    make_user(client)
    note = add_note(client)
    token = csrf_of(client)
    res = client.post(f"/notes/{note.id}/favorite", headers={"X-CSRFToken": token, "X-Requested-With": "fetch"})
    assert res.get_json() == {"ok": True, "is_favorite": True}
    res = client.post(f"/notes/{note.id}/favorite", headers={"X-CSRFToken": token, "X-Requested-With": "fetch"})
    assert res.get_json()["is_favorite"] is False


def test_pagination(client):
    make_user(client)
    for i in range(30):
        add_note(client, f"Catatan {i:02d}", "x")
    assert len(titles(client)) == 12
    assert len(titles(client, "page=3")) == 6
    assert "30</strong> catatan" in client.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ kategori
def test_categories_flow(client):
    make_user(client)
    post(client, "/categories", {"name": "Kerja"})
    dup = post(client, "/categories", {"name": "kerja"})
    assert Category.query.count() == 1
    cat = Category.query.one()
    n1 = add_note(client, "Rapat", "x", category_id=str(cat.id))
    add_note(client, "Pribadi", "x")
    assert titles(client, f"category={cat.id}") == ["Rapat"]
    post(client, f"/categories/{cat.id}/delete")
    db.session.refresh(n1)
    assert n1.category_id is None and Note.query.count() == 2  # catatan tetap ada


# ------------------------------------------------------------------ ekspor & profil
def test_export_formats(client):
    make_user(client)
    note = add_note(client, "Judul Ekspor", "Baris 1\nBaris 2 — dengan “tanda” khusus")
    txt = client.get(f"/notes/{note.id}/export/txt")
    assert txt.status_code == 200 and b"Judul Ekspor" in txt.data and "attachment" in txt.headers["Content-Disposition"]
    md = client.get(f"/notes/{note.id}/export/md")
    assert md.data.startswith(b"# Judul Ekspor")
    pdf = client.get(f"/notes/{note.id}/export/pdf")
    assert pdf.data.startswith(b"%PDF") and pdf.mimetype == "application/pdf"
    assert client.get(f"/notes/{note.id}/export/exe").status_code == 404
    assert client.get("/export/all/pdf").data.startswith(b"%PDF")


def test_profile_update_and_validation(client):
    user = make_user(client)
    res = post(client, "/profile", {"name": "Nama Baru", "birth_date": "1999-12-31"}, page="/profile")
    assert res.status_code == 302
    db.session.refresh(user)
    assert user.name == "Nama Baru"
    bad = post(client, "/profile", {"name": "", "birth_date": "2999-01-01"}, page="/profile")
    assert bad.status_code == 200 and "Nama wajib diisi." in bad.get_data(as_text=True)


def test_regenerate_recovery_invalidates_old_code(app, client):
    make_user(client)
    old = re.search(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", client.get("/welcome").get_data(as_text=True)).group(0)
    post(client, "/profile/recovery", page="/profile")
    new = re.search(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", client.get("/profile").get_data(as_text=True)).group(0)
    assert new != old
    other = app.test_client()
    h = {"X-CSRFToken": csrf_of(other)}
    assert other.post("/recover", json={"code": old}, headers=h).status_code == 404
    assert other.post("/recover", json={"code": new}, headers=h).status_code == 200


def test_delete_account_removes_everything(client):
    make_user(client)
    add_note(client)
    post(client, "/categories", {"name": "k"})
    bad = post(client, "/profile/delete", {"confirm": "nope"}, page="/profile")
    assert AnonymousUser.query.count() == 1
    post(client, "/profile/delete", {"confirm": "hapus"}, page="/profile")
    assert AnonymousUser.query.count() == 0 and Note.query.count() == 0 and Category.query.count() == 0
    assert client.get("/").status_code == 302


def test_security_headers_and_error_pages(client):
    res = client.get("/onboarding")
    assert res.headers["X-Frame-Options"] == "DENY" and "Content-Security-Policy" in res.headers
    assert res.headers["Cache-Control"] == "no-store"
    nf = client.get("/tidak-ada")
    assert nf.status_code == 404 and "Tidak ditemukan" in nf.get_data(as_text=True)
