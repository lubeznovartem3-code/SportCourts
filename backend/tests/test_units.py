"""Тесты чистой логики без базы данных и HTTP."""
import io
import logging
import os
import time

import pytest
from PIL import Image

from app import passwords, tokens, validators
from app.config import ConfigError, load_settings
from app.files import FileStore, media_url
from app.images import ImageError, ImageLimits, process_image
from app.logging_setup import RedactingFilter, redact, setup_logging
from app.ratelimit import SlidingWindowLimiter
from app.sqlfile import split_statements

LIMITS = ImageLimits(max_bytes=5 * 1024 * 1024, max_dimension=1600, max_pixels=40_000_000, jpeg_quality=82)


def mk(fmt, size=(3000, 2000), mode="RGB", **kw):
    buf = io.BytesIO()
    Image.new(mode, size, (200, 30, 30) if mode != "RGBA" else (200, 30, 30, 128)).save(buf, format=fmt, **kw)
    return buf.getvalue()


def err(data, limits=LIMITS):
    try:
        process_image(data, limits)
    except ImageError as exc:
        return exc.code
    return None


# --------------------------------------------------------------------------- валидаторы
def test_login_rules():
    assert validators.validate_login("Alex") == "Alex" and validators.validate_login("Alex") != validators.validate_login("alex")
    assert validators.validate_login("  Иван_1  ") == "Иван_1"
    for bad in ("ab", "x" * 33, "a b", "a<b", "a/b", "a:b", "a\nb"):
        with pytest.raises(ValueError):
            validators.validate_login(bad)


def test_password_rules():
    assert validators.validate_password("12345678")        # без требований к составу
    with pytest.raises(ValueError):
        validators.validate_password("1234567")
    with pytest.raises(ValueError):
        validators.validate_password("x" * 129)


def test_like_pattern_escapes():
    assert validators.like_pattern("50%_\\x") == "%50\\%\\_\\\\x%"


# --------------------------------------------------------------------------- пароли и токены
def test_argon2_hash_and_verify():
    h = passwords.hash_password("секретный пароль")
    assert h.startswith("$argon2id$") and "секретный" not in h
    assert passwords.verify_password(h, "секретный пароль") and not passwords.verify_password(h, "другой пароль1")
    assert not passwords.verify_password("!", "anything") and not passwords.verify_password("garbage", "x")
    assert passwords.hash_password("x" * 8) != passwords.hash_password("x" * 8)       # соль


def test_temporary_password_is_random_and_unambiguous():
    pw = {passwords.generate_temporary_password() for _ in range(50)}
    assert len(pw) == 50 and all(len(p) == 12 and not set(p) & set("0O1lI") for p in pw)


def test_jwt_roundtrip_and_tampering():
    from datetime import datetime, timedelta, timezone
    key = "k" * 40
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    tok = tokens.create_access_token(key, 7, 11, exp)
    payload = tokens.decode_access_token(key, tok)
    assert payload and payload["user_id"] == 7 and payload["sid"] == 11
    assert tokens.decode_access_token("other" * 10, tok) is None
    assert tokens.decode_access_token(key, tok[:-3] + "abc") is None
    assert tokens.decode_access_token(key, tokens.create_access_token(key, 1, 1, datetime.now(timezone.utc) - timedelta(seconds=5))) is None
    assert tokens.decode_access_token(key, "") is None
    import jwt
    none_alg = jwt.encode({"sub": "1", "sid": 1, "exp": int(exp.timestamp())}, key=None, algorithm="none")
    assert tokens.decode_access_token(key, none_alg) is None                          # алгоритм none отвергается


# --------------------------------------------------------------------------- изображения и файлы
def test_image_pipeline():
    out = process_image(mk("PNG"), LIMITS)
    im = Image.open(io.BytesIO(out))
    assert im.format == "JPEG" and max(im.size) <= 1600
    assert Image.open(io.BytesIO(process_image(mk("PNG", mode="RGBA"), LIMITS))).mode == "RGB"
    assert Image.open(io.BytesIO(process_image(mk("WEBP", (400, 300)), LIMITS))).format == "JPEG"


@pytest.mark.parametrize("data,code", [
    (b"", "empty_file"), (b"MZ\x90\x00" + os.urandom(300), "invalid_image"),
    (b"<html><script>alert(1)</script></html>", "invalid_image"), (b"x" * (5 * 1024 * 1024 + 1), "file_too_large"),
])
def test_image_rejections(data, code):
    assert err(data) == code


def test_image_format_and_pixel_limits():
    assert err(mk("GIF", (50, 50), mode="P")) == "unsupported_format"
    assert err(mk("PNG", (2000, 2000)), ImageLimits(5 * 1024 * 1024, 1600, 1_000_000, 82)) == "image_too_large"
    good = mk("JPEG", (800, 800))
    assert err(good[: len(good) // 3]) is not None


def test_exif_stripped_and_rotation_applied():
    ex = Image.Exif()
    ex[0x0112] = 6
    ex[0x010F] = "SECRETCAM"
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (10, 200, 10)).save(buf, format="JPEG", exif=ex)
    out = process_image(buf.getvalue(), LIMITS)
    r = Image.open(io.BytesIO(out))
    assert r.size == (100, 200) and not r.getexif() and b"SECRETCAM" not in out


def test_filestore(tmp_path):
    fs = FileStore(tmp_path)
    jpeg = process_image(mk("PNG", (100, 100)), LIMITS)
    name = fs.save("venues", jpeg)
    assert fs.resolve("venues", name)
    for bad in ("../../etc/passwd", "a.jpg", name.upper(), "/etc/passwd", name + "/x", ""):
        assert fs.resolve("venues", bad) is None
    assert fs.resolve("staging", name) is None and fs.resolve("..", name) is None
    tok = fs.stage(7, jpeg)
    assert fs.adopt(tok, 8, "venues") is None and fs.adopt("7_../x", 7, "venues") is None
    got = fs.adopt(tok, 7, "venues")
    assert got and fs.resolve("venues", got) and fs.adopt(tok, 7, "venues") is None
    fs.delete("venues", got)
    fs.delete("venues", "../../x")
    assert fs.resolve("venues", got) is None
    old = fs.staging / (fs.stage(1, jpeg) + ".jpg")
    junk = fs.staging / ".x.tmp"
    junk.write_bytes(b"1")
    for p in (old, junk):
        os.utime(p, (time.time() - 50 * 3600,) * 2)
    assert fs.cleanup_staging(24) == 2 and not list(fs.staging.iterdir())
    with pytest.raises(Exception):
        fs._write_atomic(fs.staging, "x.jpg", None)                                 # type: ignore[arg-type]
    assert not list(fs.staging.iterdir())                                           # временный файл не остался
    assert media_url("avatars", "a.jpg") == "/media/avatars/a.jpg" and media_url("avatars", None) is None


# --------------------------------------------------------------------------- логи, лимиты, конфиг, миграции
def test_log_redaction():
    cases = [
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("login password=hunter2 ok", "hunter2"),
        ('{"password": "hunter2"}', "hunter2"),
        ("postgresql+asyncpg://sportcourts:topsecret@127.0.0.1/db", "topsecret"),
        ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghij", "eyJzdWIi"),
        ("SECRET_KEY=abcdefghijklmnop", "abcdefghijklmnop"),
    ]
    for text_, secret in cases:
        assert secret not in redact(text_), text_
    rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "bad %s", ("password=hunter2",), None)
    RedactingFilter().filter(rec)
    assert "hunter2" not in rec.getMessage()


def test_log_rotation_and_no_secrets_in_file(tmp_path):
    path = setup_logging(tmp_path, "INFO", max_mb=1, backup_count=2)
    lg = logging.getLogger("sportcourts.test")
    try:
        raise ValueError("password=hunter2")
    except ValueError:
        lg.exception("упало, token=abc123")
    for h in logging.getLogger().handlers:
        h.flush()
    content = path.read_text(encoding="utf-8")
    assert "hunter2" not in content and "abc123" not in content and "Traceback" in content
    from logging.handlers import RotatingFileHandler
    assert any(isinstance(h, RotatingFileHandler) and h.backupCount == 2 for h in logging.getLogger().handlers)


def test_rate_limiter_window():
    now = [0.0]
    lim = SlidingWindowLimiter(clock=lambda: now[0])
    for _ in range(3):
        lim.hit("k", 10)
    assert lim.count("k", 10) == 3 and 1 <= lim.retry_after("k", 10) <= 11
    now[0] = 11
    assert lim.count("k", 10) == 0 and lim.retry_after("k", 10) == 0
    lim.hit("k", 10)
    lim.reset("k")
    assert lim.count("k", 10) == 0


def test_config_validation(tmp_path):
    env = {"DATABASE_URL": "postgresql://u:p@localhost/db", "SECRET_KEY": "s" * 40}
    s = load_settings(environ=env, env_file=os.devnull)
    assert s.database_url == "postgresql+asyncpg://u:p@localhost/db" and s.port == 8000 and s.presence_ttl_hours == 3
    for bad, msg in (({"SECRET_KEY": "short"}, "SECRET_KEY"), ({"SECRET_KEY": "CHANGE_ME" + "x" * 40}, "заглушк"),
                     ({"PORT": "99999"}, "PORT"), ({"DATABASE_URL": "mysql://x"}, "DATABASE_URL")):
        with pytest.raises(ConfigError, match=msg):
            load_settings(environ={**env, **bad}, env_file=os.devnull)
    with pytest.raises(ConfigError, match="обязательные"):
        load_settings(environ={}, env_file=os.devnull)
    f = tmp_path / ".env"
    f.write_text("DATABASE_URL=postgresql://a:b@h/d\nSECRET_KEY=" + "k" * 40 + "\nPORT=9001\n", encoding="utf-8")
    assert load_settings(environ={"PORT": "9002"}, env_file=f).port == 9002          # окружение приоритетнее файла
    assert load_settings(environ={}, env_file=f).port == 9001


def test_sql_split():
    sql = "-- c\nCREATE TABLE a (x int);\n--;;\n-- only comment\n--;;\nCREATE INDEX i ON a (x);\n"
    assert split_statements(sql) == ["CREATE TABLE a (x int);", "CREATE INDEX i ON a (x);"]
