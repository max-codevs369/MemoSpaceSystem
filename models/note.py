from sqlalchemy.dialects import mysql

from extensions import db
from utils import now_local
from .user import BigInt

LongText = db.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


class Note(db.Model):
    __tablename__ = "notes"
    __table_args__ = (
        db.Index("ix_notes_user_created", "user_id", "created_at"),
        db.Index("ix_notes_user_title", "user_id", "title"),
        db.Index("ix_notes_user_fav", "user_id", "is_favorite"),
        db.Index("ix_notes_user_deleted", "user_id", "deleted_at"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigInt, db.ForeignKey("anonymous_users.id", ondelete="CASCADE"), nullable=False
    )
    category_id = db.Column(
        BigInt, db.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(LongText, nullable=True)
    is_favorite = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_local, onupdate=now_local)
    deleted_at = db.Column(db.DateTime, nullable=True)  

    owner = db.relationship("AnonymousUser", back_populates="notes")
    category = db.relationship("Category", back_populates="notes")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def was_edited(self) -> bool:
        return self.updated_at and self.created_at and self.updated_at > self.created_at
