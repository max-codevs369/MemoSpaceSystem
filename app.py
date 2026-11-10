import click
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from sqlalchemy.engine import make_url

from config import Config
from extensions import csrf, db
from utils import fmt_date, fmt_date_short, fmt_time, now_local


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY belum diset. Salin .env.example menjadi .env lalu isi SECRET_KEY "
            "(python -c \"import secrets; print(secrets.token_hex(32))\")."
        )

    db.init_app(app)
    csrf.init_app(app)

    import models  
    from routes import categories, notes, onboarding, profile

    for module in (onboarding, notes, categories, profile):
        app.register_blueprint(module.bp)

    _register_template_helpers(app)
    _register_security_headers(app)
    _register_error_handlers(app)
    _register_cli(app)

    if app.config["AUTO_CREATE_TABLES"]:
        with app.app_context():
            try:
                db.create_all()
            except Exception as exc:  
                app.logger.error(
                    "Gagal membuat tabel: %s\nJalankan `flask --app app init-db` untuk membuat database.", exc
                )
    return app


def _register_template_helpers(app):
    from services.note_service import snippet

    app.jinja_env.filters.update(
        tgl=fmt_date, tgl_pendek=fmt_date_short, jam=fmt_time, snippet=snippet
    )

    @app.context_processor
    def inject_user():
        from services import identity_service

        return {"current_user": identity_service.current_user(), "now": now_local()}


def _register_security_headers(app):
    from flask import g

    @app.before_request
    def reset_identity_cache():
        g.pop("current_user", None) 

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        if request.endpoint not in (None, "static"):
            resp.headers["Cache-Control"] = "no-store"  
        return resp


def _register_error_handlers(app):
    def respond(status, title, message):
        wants_json = request.is_json or request.headers.get("X-Requested-With") == "fetch"
        if wants_json:
            return jsonify(ok=False, error=message), status
        return render_template("error.html", status=status, title=title, message=message), status

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return respond(400, "Sesi kedaluwarsa", "Token keamanan tidak valid. Muat ulang halaman lalu coba lagi.")

    @app.errorhandler(404)
    def not_found(_e):
        return respond(404, "Tidak ditemukan", "Halaman atau catatan yang kamu cari tidak ada.")

    @app.errorhandler(405)
    def not_allowed(_e):
        return respond(405, "Metode tidak diizinkan", "Permintaan ini tidak diizinkan.")

    @app.errorhandler(413)
    def too_large(_e):
        return respond(413, "Data terlalu besar", "Data yang dikirim melebihi batas ukuran.")

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return respond(500, "Terjadi kesalahan", "Ada masalah di server. Coba lagi beberapa saat lagi.")


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        if url.get_backend_name() == "mysql":
            import pymysql

            conn = pymysql.connect(
                host=url.host, port=url.port or 3306, user=url.username, password=url.password or "",
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                conn.commit()
            finally:
                conn.close()
        db.create_all()
        click.echo("Database dan tabel siap dipakai.")


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=5000, debug=application.config["DEBUG"])
