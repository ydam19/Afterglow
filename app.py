"""
Afterglow — 하루의 여운
하루 한 장의 사진 + 한 줄 감정 기록을 필름 감성으로 아카이빙하는 Flask 앱.
"""
import os
import random
import sqlite3
import calendar as cal
from datetime import date, datetime
from uuid import uuid4

from flask import (
    Flask, render_template, request, redirect, url_for, flash, g, abort
)
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "diary.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
THUMB_MAX = 1200  # 긴 변 기준 리사이즈 최대 px

# 감정(무드) 정의: 키 -> 라벨 (이모지·색상 없이 텍스트만, 톤 통일)
MOODS = {
    "flutter": "설렘",
    "calm":    "평온",
    "warm":    "충만",
    "longing": "그리움",
    "blue":    "울적",
    "empty":   "공허",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "film-mood-diary-dev-key"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB


# ---------- DB helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            mood       TEXT NOT NULL,
            note       TEXT NOT NULL DEFAULT '',
            image      TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.commit()
    db.close()


# 히어로에 띄울 시적인 문구 (하루의 끝·노을·기록)
QUOTES = [
    "저무는 것들은 모두, 조금씩 빛난다.",
    "하루의 끝에서 가장 따뜻한 빛이 남는다.",
    "사라지는 순간을 가만히 붙잡아 두는 일.",
    "오늘도 노을이 질 때까지, 당신은 충분했다.",
    "지는 해를 바라보는 것만으로 괜찮아지는 저녁이 있다.",
    "흘려보낸 하루에도 한 컷은 남는다.",
]


# ---------- 템플릿 전역 ----------
@app.context_processor
def inject_globals():
    today = date.today()
    return {
        "MOODS": MOODS,
        "today": today.isoformat(),
        "today_label": today.strftime("%d %b %Y").upper(),  # 05 NOV 2026
        "quote": random.choice(QUOTES),
    }


# ---------- 이미지 처리 ----------
def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_image(file_storage):
    """업로드 이미지를 EXIF 회전 보정 + 리사이즈 후 저장. 저장된 파일명 반환."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed(file_storage.filename):
        raise ValueError("지원하지 않는 이미지 형식이에요 (png/jpg/gif/webp).")

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, fname)

    img = Image.open(file_storage.stream)
    img = ImageOps.exif_transpose(img)  # 세로 사진 회전 보정
    img.thumbnail((THUMB_MAX, THUMB_MAX))
    if ext in ("jpg", "jpeg"):
        img = img.convert("RGB")
    img.save(path)
    return fname


# ---------- 라우트 ----------
@app.route("/")
def index():
    mood_filter = request.args.get("mood")
    db = get_db()
    if mood_filter in MOODS:
        rows = db.execute(
            "SELECT * FROM entries WHERE mood = ? ORDER BY entry_date DESC, id DESC",
            (mood_filter,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC, id DESC"
        ).fetchall()
    return render_template("index.html", entries=rows, active_mood=mood_filter)


@app.route("/archive")
def archive():
    mood_filter = request.args.get("mood")
    db = get_db()
    if mood_filter in MOODS:
        rows = db.execute(
            "SELECT * FROM entries WHERE mood = ? ORDER BY entry_date DESC, id DESC",
            (mood_filter,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC, id DESC"
        ).fetchall()
    return render_template("archive.html", entries=rows, active_mood=mood_filter)


@app.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        entry_date = request.form.get("entry_date", "").strip()
        mood = request.form.get("mood", "").strip()
        note = request.form.get("note", "").strip()

        if not entry_date:
            entry_date = date.today().isoformat()
        if mood not in MOODS:
            flash("오늘의 무드를 골라주세요.")
            return redirect(url_for("new"))

        try:
            image = save_image(request.files.get("image"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("new"))

        db = get_db()
        db.execute(
            "INSERT INTO entries (entry_date, mood, note, image, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (entry_date, mood, note, image, datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        flash("오늘의 한 컷이 기록됐어요")
        return redirect(url_for("index"))

    return render_template("new.html")


@app.route("/entry/<int:entry_id>")
def detail(entry_id):
    db = get_db()
    row = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        abort(404)
    return render_template("detail.html", e=row)


@app.route("/entry/<int:entry_id>/delete", methods=["POST"])
def delete(entry_id):
    db = get_db()
    row = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        abort(404)
    if row["image"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["image"]))
        except OSError:
            pass
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()
    flash("기록을 지웠어요.")
    return redirect(url_for("index"))


@app.route("/calendar")
def calendar_view():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    db = get_db()
    prefix = f"{year:04d}-{month:02d}"
    rows = db.execute(
        "SELECT * FROM entries WHERE entry_date LIKE ? ORDER BY id DESC",
        (prefix + "%",),
    ).fetchall()

    # 날짜(일) -> 대표 기록(그 달 최신) 매핑
    by_day = {}
    for r in rows:
        try:
            d = datetime.strptime(r["entry_date"], "%Y-%m-%d").day
        except ValueError:
            continue
        by_day.setdefault(d, r)

    weeks = cal.Calendar(firstweekday=6).monthdayscalendar(year, month)  # 일요일 시작

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return render_template(
        "calendar.html",
        year=year, month=month, weeks=weeks, by_day=by_day,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today=today,
    )


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    init_db()
    # 배포 시 모든 인터페이스(0.0.0.0)로 공개 → 공용 IP로 접속 가능
    # macOS 로컬은 5000번을 AirPlay가 점유하므로 8000번 사용
    # 로컬 개발에서 자동 리로드가 필요하면 FLASK_DEBUG=1 로 실행
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
