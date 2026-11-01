"""Начальная схема SportCourts.

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

from app.sqlfile import run_sql_file

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).with_suffix(".sql")

# Порядок важен: сначала таблицы, которые ссылаются на другие.
TABLES_DROP_ORDER = [
    "audit_log", "reports", "notifications", "messages", "user_blocks",
    "friend_requests", "friendships", "game_participants", "games",
    "player_reports", "presence_checkins", "moderator_requests",
    "moderation_decisions", "venue_change_proposal_sports",
    "venue_change_proposals", "venue_submission_sports", "venue_submissions",
    "venue_sports", "venues", "user_favorite_sports", "sports",
    "user_sessions", "users",
]


def upgrade() -> None:
    run_sql_file(op, SQL_FILE)


def downgrade() -> None:
    for table in TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS enforce_game_capacity() CASCADE")
