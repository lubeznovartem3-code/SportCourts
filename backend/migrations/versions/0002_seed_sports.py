"""Справочник видов спорта (футбол, баскетбол, волейбол).

Это справочные данные, а не площадки: список можно расширять через
административный интерфейс без изменения кода. Миграция идемпотентна.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SEED = [
    ("football", "Футбол", 10),
    ("basketball", "Баскетбол", 20),
    ("volleyball", "Волейбол", 30),
]


def upgrade() -> None:
    for code, name, order in SEED:
        op.execute(
            "INSERT INTO sports (code, name, sort_order) "
            f"VALUES ('{code}', '{name}', {order}) ON CONFLICT (code) DO NOTHING"
        )


def downgrade() -> None:
    # Удаляем только если вид спорта нигде не используется.
    for code, _name, _order in SEED:
        op.execute(
            f"DELETE FROM sports WHERE code = '{code}' "
            "AND NOT EXISTS (SELECT 1 FROM venue_sports vs WHERE vs.sport_id = sports.id) "
            "AND NOT EXISTS (SELECT 1 FROM venue_submission_sports s WHERE s.sport_id = sports.id) "
            "AND NOT EXISTS (SELECT 1 FROM venue_change_proposal_sports c WHERE c.sport_id = sports.id)"
        )
