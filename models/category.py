from extensions import db
from utils import now_local
from .user import BigInt


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_category_user_name"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigInt, db.ForeignKey("anonymous_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_local)

    owner = db.relationship("AnonymousUser", back_populates="categories")
    notes = db.relationship("Note", back_populates="category", passive_deletes=True)
