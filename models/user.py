from sqlalchemy import BigInteger, Integer

from extensions import db
from utils import now_local

BigInt = BigInteger().with_variant(Integer, "sqlite")


class AnonymousUser(db.Model):
    __tablename__ = "anonymous_users"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    anonymous_id = db.Column(db.CHAR(36), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    birth_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)

    recovery_code_hash = db.Column(db.CHAR(64), nullable=True)   
    onboarding_nonce = db.Column(db.CHAR(32), unique=True, nullable=True) 

    notes = db.relationship(
        "Note", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic"
    )
    categories = db.relationship(
        "Category", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic"
    )
    tokens = db.relationship(
        "IdentityToken", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class IdentityToken(db.Model):

    __tablename__ = "identity_tokens"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigInt, db.ForeignKey("anonymous_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = db.Column(db.CHAR(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=now_local)

    owner = db.relationship("AnonymousUser", back_populates="tokens")
