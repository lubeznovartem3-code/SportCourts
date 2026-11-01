-- SportCourts: начальная схема PostgreSQL.
-- Файл исполняется миграцией 0001_initial.py. Команды разделены строкой "--;;"
-- (драйвер asyncpg не умеет выполнять несколько команд за один вызов).
-- Тот же файл можно применить вручную: psql -f 0001_initial.sql

-- ---------------------------------------------------------------- пользователи
CREATE TABLE users (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login                 TEXT        NOT NULL,
    password_hash         TEXT        NOT NULL,
    display_name          TEXT        NOT NULL,
    avatar_path           TEXT,
    role                  TEXT        NOT NULL DEFAULT 'user',
    can_review_reports    BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active             BOOLEAN     NOT NULL DEFAULT TRUE,
    must_change_password  BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at          TIMESTAMPTZ,
    deleted_at            TIMESTAMPTZ,
    CONSTRAINT users_role_chk CHECK (role IN ('user', 'moderator', 'admin')),
    CONSTRAINT users_login_len_chk CHECK (char_length(login) BETWEEN 3 AND 64),
    CONSTRAINT users_display_name_len_chk CHECK (char_length(display_name) BETWEEN 1 AND 64)
);
--;;
-- Уникальность логина с учётом регистра ("Alex" и "alex" — разные логины).
CREATE UNIQUE INDEX users_login_key ON users (login);
--;;
CREATE INDEX users_display_name_idx ON users (lower(display_name));
--;;
CREATE TABLE user_sessions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    last_used_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at    TIMESTAMPTZ,
    user_agent    TEXT
);
--;;
CREATE INDEX user_sessions_active_idx ON user_sessions (user_id) WHERE revoked_at IS NULL;
--;;
-- ---------------------------------------------------------------- виды спорта
CREATE TABLE sports (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT sports_code_key UNIQUE (code),
    CONSTRAINT sports_name_key UNIQUE (name),
    CONSTRAINT sports_name_len_chk CHECK (char_length(name) BETWEEN 1 AND 40)
);
--;;
CREATE TABLE user_favorite_sports (
    user_id   BIGINT  NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    sport_id  INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, sport_id)
);
--;;
-- ---------------------------------------------------------------- площадки
CREATE TABLE venues (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         TEXT             NOT NULL,
    address      TEXT             NOT NULL,
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    venue_type   TEXT             NOT NULL,
    description  TEXT,
    work_hours   TEXT,
    cost_info    TEXT,
    photo_path   TEXT,
    status       TEXT             NOT NULL DEFAULT 'active',
    created_by   BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT venues_lat_chk CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT venues_lon_chk CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT venues_type_chk CHECK (venue_type IN ('indoor', 'outdoor')),
    CONSTRAINT venues_status_chk CHECK (status IN ('active', 'archived')),
    CONSTRAINT venues_name_len_chk CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT venues_address_len_chk CHECK (char_length(address) BETWEEN 1 AND 255)
);
--;;
CREATE INDEX venues_status_geo_idx ON venues (status, latitude, longitude);
--;;
CREATE INDEX venues_name_idx ON venues (lower(name));
--;;
CREATE TABLE venue_sports (
    venue_id  BIGINT  NOT NULL REFERENCES venues (id) ON DELETE CASCADE,
    sport_id  INTEGER NOT NULL REFERENCES sports (id),
    PRIMARY KEY (venue_id, sport_id)
);
--;;
CREATE INDEX venue_sports_sport_idx ON venue_sports (sport_id);
--;;
-- Заявки на добавление новой площадки (не видны в публичном каталоге).
CREATE TABLE venue_submissions (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    submitter_id     BIGINT           NOT NULL REFERENCES users (id),
    name             TEXT             NOT NULL,
    address          TEXT             NOT NULL,
    latitude         DOUBLE PRECISION NOT NULL,
    longitude        DOUBLE PRECISION NOT NULL,
    venue_type       TEXT             NOT NULL,
    description      TEXT,
    work_hours       TEXT,
    cost_info        TEXT,
    photo_path       TEXT,
    status           TEXT             NOT NULL DEFAULT 'pending',
    decided_by       BIGINT REFERENCES users (id) ON DELETE SET NULL,
    decided_at       TIMESTAMPTZ,
    decision_reason  TEXT,
    venue_id         BIGINT REFERENCES venues (id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT vsub_lat_chk CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT vsub_lon_chk CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT vsub_type_chk CHECK (venue_type IN ('indoor', 'outdoor')),
    CONSTRAINT vsub_status_chk CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT vsub_decided_chk CHECK (status = 'pending' OR decided_at IS NOT NULL),
    CONSTRAINT vsub_reject_reason_chk CHECK (status <> 'rejected' OR char_length(btrim(coalesce(decision_reason, ''))) > 0)
);
--;;
CREATE INDEX venue_submissions_status_idx ON venue_submissions (status, id);
--;;
CREATE INDEX venue_submissions_submitter_idx ON venue_submissions (submitter_id, id DESC);
--;;
CREATE TABLE venue_submission_sports (
    submission_id  BIGINT  NOT NULL REFERENCES venue_submissions (id) ON DELETE CASCADE,
    sport_id       INTEGER NOT NULL REFERENCES sports (id),
    PRIMARY KEY (submission_id, sport_id)
);
--;;
-- Предложения изменений существующей площадки: полный снимок новых значений.
CREATE TABLE venue_change_proposals (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venue_id         BIGINT           NOT NULL REFERENCES venues (id) ON DELETE CASCADE,
    proposer_id      BIGINT           NOT NULL REFERENCES users (id),
    name             TEXT             NOT NULL,
    address          TEXT             NOT NULL,
    latitude         DOUBLE PRECISION NOT NULL,
    longitude        DOUBLE PRECISION NOT NULL,
    venue_type       TEXT             NOT NULL,
    description      TEXT,
    work_hours       TEXT,
    cost_info        TEXT,
    photo_path       TEXT,
    status           TEXT             NOT NULL DEFAULT 'pending',
    decided_by       BIGINT REFERENCES users (id) ON DELETE SET NULL,
    decided_at       TIMESTAMPTZ,
    decision_reason  TEXT,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT vchg_lat_chk CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT vchg_lon_chk CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT vchg_type_chk CHECK (venue_type IN ('indoor', 'outdoor')),
    CONSTRAINT vchg_status_chk CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT vchg_decided_chk CHECK (status = 'pending' OR decided_at IS NOT NULL),
    CONSTRAINT vchg_reject_reason_chk CHECK (status <> 'rejected' OR char_length(btrim(coalesce(decision_reason, ''))) > 0)
);
--;;
CREATE INDEX venue_change_proposals_status_idx ON venue_change_proposals (status, id);
--;;
CREATE INDEX venue_change_proposals_proposer_idx ON venue_change_proposals (proposer_id, id DESC);
--;;
CREATE INDEX venue_change_proposals_venue_idx ON venue_change_proposals (venue_id);
--;;
CREATE TABLE venue_change_proposal_sports (
    proposal_id  BIGINT  NOT NULL REFERENCES venue_change_proposals (id) ON DELETE CASCADE,
    sport_id     INTEGER NOT NULL REFERENCES sports (id),
    PRIMARY KEY (proposal_id, sport_id)
);
--;;
-- История решений модерации (неизменяемый журнал).
CREATE TABLE moderation_decisions (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind           TEXT        NOT NULL,
    submission_id  BIGINT REFERENCES venue_submissions (id) ON DELETE CASCADE,
    proposal_id    BIGINT REFERENCES venue_change_proposals (id) ON DELETE CASCADE,
    moderator_id   BIGINT REFERENCES users (id) ON DELETE SET NULL,
    decision       TEXT        NOT NULL,
    reason         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mdec_kind_chk CHECK (kind IN ('venue_submission', 'venue_change')),
    CONSTRAINT mdec_decision_chk CHECK (decision IN ('approved', 'rejected')),
    CONSTRAINT mdec_target_chk CHECK (
        (kind = 'venue_submission' AND submission_id IS NOT NULL AND proposal_id IS NULL) OR
        (kind = 'venue_change' AND proposal_id IS NOT NULL AND submission_id IS NULL)
    )
);
--;;
CREATE INDEX moderation_decisions_created_idx ON moderation_decisions (id DESC);
--;;
-- Заявки пользователей на роль модератора.
CREATE TABLE moderator_requests (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    message          TEXT,
    status           TEXT        NOT NULL DEFAULT 'pending',
    decided_by       BIGINT REFERENCES users (id) ON DELETE SET NULL,
    decided_at       TIMESTAMPTZ,
    decision_reason  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT modreq_status_chk CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT modreq_decided_chk CHECK (status = 'pending' OR decided_at IS NOT NULL)
);
--;;
CREATE UNIQUE INDEX moderator_requests_one_pending ON moderator_requests (user_id) WHERE status = 'pending';
--;;
-- ---------------------------------------------------------------- присутствие и отчёты
-- Личные отметки "я на площадке". Активная = ended_at IS NULL AND expires_at > now().
CREATE TABLE presence_checkins (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT      NOT NULL REFERENCES users (id),
    venue_id    BIGINT      NOT NULL REFERENCES venues (id),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    ended_at    TIMESTAMPTZ,
    end_reason  TEXT,
    CONSTRAINT presence_reason_chk CHECK (end_reason IN ('manual', 'expired', 'moved')),
    CONSTRAINT presence_end_pair_chk CHECK ((ended_at IS NULL) = (end_reason IS NULL)),
    CONSTRAINT presence_expiry_chk CHECK (expires_at > started_at)
);
--;;
-- Не более одной незакрытой отметки на пользователя (а значит и на площадку).
CREATE UNIQUE INDEX presence_one_open_per_user ON presence_checkins (user_id) WHERE ended_at IS NULL;
--;;
CREATE INDEX presence_venue_open_idx ON presence_checkins (venue_id, expires_at) WHERE ended_at IS NULL;
--;;
CREATE INDEX presence_user_history_idx ON presence_checkins (user_id, started_at DESC);
--;;
-- Отчёты "сколько людей на площадке примерно" (включая тех, кто не в приложении).
CREATE TABLE player_reports (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venue_id      BIGINT      NOT NULL REFERENCES venues (id),
    reporter_id   BIGINT      NOT NULL REFERENCES users (id),
    player_count  SMALLINT    NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT player_reports_count_chk CHECK (player_count BETWEEN 0 AND 200)
);
--;;
CREATE INDEX player_reports_venue_idx ON player_reports (venue_id, created_at DESC);
--;;
CREATE INDEX player_reports_reporter_idx ON player_reports (reporter_id, created_at DESC);
--;;
-- ---------------------------------------------------------------- игры
CREATE TABLE games (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venue_id      BIGINT      NOT NULL REFERENCES venues (id),
    organizer_id  BIGINT      NOT NULL REFERENCES users (id),
    title         TEXT        NOT NULL,
    starts_at     TIMESTAMPTZ NOT NULL,
    max_players   SMALLINT    NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'open',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at     TIMESTAMPTZ,
    CONSTRAINT games_title_len_chk CHECK (char_length(title) BETWEEN 1 AND 80),
    CONSTRAINT games_max_players_chk CHECK (max_players BETWEEN 2 AND 100),
    CONSTRAINT games_status_chk CHECK (status IN ('open', 'cancelled', 'finished')),
    CONSTRAINT games_closed_chk CHECK ((status = 'open') = (closed_at IS NULL))
);
--;;
CREATE INDEX games_open_idx ON games (starts_at) WHERE status = 'open';
--;;
CREATE INDEX games_venue_idx ON games (venue_id, starts_at DESC);
--;;
CREATE INDEX games_organizer_idx ON games (organizer_id, id DESC);
--;;
CREATE TABLE game_participants (
    game_id    BIGINT      NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    user_id    BIGINT      NOT NULL REFERENCES users (id),
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, user_id)
);
--;;
CREATE INDEX game_participants_user_idx ON game_participants (user_id);
--;;
-- Страховка на уровне БД: даже при ошибке в коде приложения участников не станет больше лимита.
-- Блокировка строки игры делает проверку безопасной при параллельных запросах.
CREATE FUNCTION enforce_game_capacity() RETURNS trigger AS $$
DECLARE
    cap INTEGER;
    cnt INTEGER;
BEGIN
    SELECT max_players INTO cap FROM games WHERE id = NEW.game_id FOR UPDATE;
    IF cap IS NULL THEN
        RETURN NEW;  -- нарушение внешнего ключа будет обработано самой БД
    END IF;
    SELECT count(*) INTO cnt FROM game_participants WHERE game_id = NEW.game_id;
    IF cnt >= cap THEN
        RAISE EXCEPTION 'game_full' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--;;
CREATE TRIGGER game_participants_capacity
    BEFORE INSERT ON game_participants
    FOR EACH ROW EXECUTE FUNCTION enforce_game_capacity();
--;;
-- ---------------------------------------------------------------- друзья, блокировки, сообщения
CREATE TABLE friendships (
    user_low_id   BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    user_high_id  BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_low_id, user_high_id),
    CONSTRAINT friendships_order_chk CHECK (user_low_id < user_high_id)
);
--;;
CREATE INDEX friendships_high_idx ON friendships (user_high_id);
--;;
CREATE TABLE friend_requests (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender_id     BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    receiver_id   BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status        TEXT        NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at  TIMESTAMPTZ,
    CONSTRAINT friend_requests_status_chk CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    CONSTRAINT friend_requests_self_chk CHECK (sender_id <> receiver_id)
);
--;;
-- Между двумя пользователями может быть только один ожидающий запрос (в любую сторону).
CREATE UNIQUE INDEX friend_requests_pending_pair
    ON friend_requests (LEAST(sender_id, receiver_id), GREATEST(sender_id, receiver_id))
    WHERE status = 'pending';
--;;
CREATE INDEX friend_requests_receiver_idx ON friend_requests (receiver_id, id DESC) WHERE status = 'pending';
--;;
CREATE INDEX friend_requests_sender_idx ON friend_requests (sender_id, id DESC) WHERE status = 'pending';
--;;
CREATE TABLE user_blocks (
    blocker_id  BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    blocked_id  BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (blocker_id, blocked_id),
    CONSTRAINT user_blocks_self_chk CHECK (blocker_id <> blocked_id)
);
--;;
CREATE INDEX user_blocks_blocked_idx ON user_blocks (blocked_id);
--;;
CREATE TABLE messages (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender_id     BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    recipient_id  BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    body          TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at       TIMESTAMPTZ,
    CONSTRAINT messages_body_len_chk CHECK (char_length(body) BETWEEN 1 AND 2000),
    CONSTRAINT messages_self_chk CHECK (sender_id <> recipient_id)
);
--;;
CREATE INDEX messages_pair_idx ON messages (sender_id, recipient_id, id DESC);
--;;
CREATE INDEX messages_unread_idx ON messages (recipient_id, sender_id) WHERE read_at IS NULL;
--;;
-- ---------------------------------------------------------------- уведомления
CREATE TABLE notifications (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type        TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    body        TEXT,
    ref_id      BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ,
    CONSTRAINT notifications_type_chk CHECK (type IN (
        'friend_request', 'friend_accepted', 'venue_submission_decided',
        'venue_change_decided', 'moderator_request_decided', 'system'
    ))
);
--;;
CREATE INDEX notifications_user_idx ON notifications (user_id, id DESC);
--;;
CREATE INDEX notifications_unread_idx ON notifications (user_id) WHERE read_at IS NULL;
--;;
-- ---------------------------------------------------------------- жалобы и аудит
CREATE TABLE reports (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reporter_id       BIGINT      NOT NULL REFERENCES users (id),
    target_user_id    BIGINT REFERENCES users (id),
    target_venue_id   BIGINT REFERENCES venues (id),
    target_game_id    BIGINT REFERENCES games (id),
    reason            TEXT        NOT NULL,
    description       TEXT,
    status            TEXT        NOT NULL DEFAULT 'open',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_by       BIGINT REFERENCES users (id) ON DELETE SET NULL,
    resolved_at       TIMESTAMPTZ,
    resolution_note   TEXT,
    CONSTRAINT reports_one_target_chk CHECK (num_nonnulls(target_user_id, target_venue_id, target_game_id) = 1),
    CONSTRAINT reports_reason_chk CHECK (reason IN ('spam', 'harassment', 'inappropriate', 'fake_info', 'other')),
    CONSTRAINT reports_status_chk CHECK (status IN ('open', 'resolved', 'dismissed')),
    CONSTRAINT reports_resolved_chk CHECK (status = 'open' OR resolved_at IS NOT NULL)
);
--;;
CREATE INDEX reports_status_idx ON reports (status, id DESC);
--;;
CREATE INDEX reports_reporter_idx ON reports (reporter_id, created_at DESC);
--;;
CREATE TABLE audit_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id     BIGINT REFERENCES users (id) ON DELETE SET NULL,
    action       TEXT        NOT NULL,
    target_type  TEXT,
    target_id    BIGINT,
    details      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
--;;
CREATE INDEX audit_log_created_idx ON audit_log (id DESC);
