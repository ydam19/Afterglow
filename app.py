"""
Afterglow — 하루의 여운
하루 한 장의 사진 + 한 줄 감정 기록을 필름 감성으로 아카이빙하는 Flask 앱.
"""
import os
import io
import re
import random
import calendar as cal
from datetime import date, datetime
from functools import lru_cache, wraps
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash, g, abort, session, jsonify
)
from PIL import Image, ImageOps, UnidentifiedImageError
from astral import Observer
from astral.sun import sunset
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from supabase import create_client, ClientOptions
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError, AuthError

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")  # anon(publishable) 키만 사용 — RLS로 보호
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(".env 에 SUPABASE_URL, SUPABASE_ANON_KEY 를 설정하세요 (.env.example 참고).")

BUCKET = "photos"
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
THUMB_MAX = 1200  # 긴 변 기준 리사이즈 최대 px
SIGNED_URL_TTL = 60 * 60  # 사진 서명 URL 유효시간(초)

# 감정(무드) 정의: 키 -> 라벨 (이모지·색상 없이 텍스트만, 톤 통일)
MOODS = {
    "flutter": "설렘",
    "calm":    "평온",
    "warm":    "충만",
    "longing": "그리움",
    "blue":    "울적",
    "empty":   "공허",
}

# 노을 시각 계산 기본 위치 (위치를 남기지 않은 기록)
DEFAULT_LAT, DEFAULT_LON, DEFAULT_TZ = 37.5665, 126.9780, "Asia/Seoul"  # 서울


def today_local():
    # 서버(Vercel)는 UTC라 date.today() 를 쓰면 한국 날짜와 어긋남
    return datetime.now(ZoneInfo(DEFAULT_TZ)).date()


def _zone(name):
    try:
        return ZoneInfo(name) if name else ZoneInfo(DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def sunset_time(day, lat=None, lon=None, tz=None):
    """그 날, 그 위치의 일몰 시각(HH:MM). 백야/극야라 해가 지지 않으면 None."""
    if lat is None or lon is None:
        lat, lon = DEFAULT_LAT, DEFAULT_LON
    if isinstance(day, str):
        day = date.fromisoformat(day[:10])
    try:
        return sunset(Observer(lat, lon), day, tzinfo=_zone(tz)).strftime("%H:%M")
    except ValueError:
        return None


# 좌표 → 시 이름 (OpenStreetMap Nominatim, 키 불필요 · 초당 1회 이하 사용 정책)
GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
GEOCODE_UA = "Afterglow/0.1 (+https://github.com/ydam19/Afterglow)"
CITY_SUFFIXES = ("특별자치시", "특별시", "광역시")  # 서울특별시 → 서울


@lru_cache(maxsize=512)
def reverse_place(lat, lon):
    """좌표가 속한 시(없으면 군·도) 이름. 실패하면 None."""
    try:
        res = httpx.get(
            GEOCODE_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10,
                    "accept-language": "ko", "addressdetails": 1},
            headers={"User-Agent": GEOCODE_UA}, timeout=4,
        )
        res.raise_for_status()
        addr = res.json().get("address", {})
    except (httpx.HTTPError, ValueError):
        app.logger.warning("reverse geocode failed for %s,%s", lat, lon)
        return None
    name = (addr.get("city") or addr.get("town") or addr.get("county")
            or addr.get("state") or addr.get("province"))
    if not name:
        return None
    for suffix in CITY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def with_sunsets(rows):
    for r in rows:
        r["sunset"] = sunset_time(r["entry_date"], r.get("lat"), r.get("lon"), r.get("tz"))
        if r.get("lat") is None:
            r["sunset_place"] = "서울"          # 위치를 안 남긴 기록은 서울 기준으로 계산
        else:
            r["sunset_place"] = r.get("place")  # 시 이름을 못 구했으면 표시 생략
    return rows


def parse_location(form):
    """폼의 위도/경도/시간대를 검증. 좌표는 소수 둘째 자리(약 1km)로 반올림해 저장."""
    # 위치 없이 시간대만 있으면 '서울 좌표 + 다른 시간대'로 어긋나므로 셋 다 비움
    try:
        lat, lon = float(form.get("lat", "")), float(form.get("lon", ""))
    except ValueError:
        return None, None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, None
    tz = form.get("tz", "").strip()
    if not tz or _zone(tz).key != tz:
        tz = None
    return round(lat, 2), round(lon, 2), tz


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ---------- Supabase helpers ----------
def new_client():
    # 요청마다 새 클라이언트 — 사용자 세션이 요청 간에 섞이지 않도록
    return create_client(
        SUPABASE_URL, SUPABASE_KEY,
        ClientOptions(persist_session=False, auto_refresh_token=False),
    )


def get_sb():
    """로그인한 사용자 권한으로 동작하는 Supabase 클라이언트 (RLS 적용)."""
    if "sb" not in g:
        sb = new_client()
        tokens = session.get("sb_tokens")
        if tokens:
            try:
                # 만료된 access token이면 refresh token으로 자동 갱신
                res = sb.auth.set_session(tokens["access"], tokens["refresh"])
                s = res.session
                session["sb_tokens"] = {"access": s.access_token, "refresh": s.refresh_token}
                session["user_email"] = res.user.email
                g.user_id = res.user.id
            except AuthError:
                session.pop("sb_tokens", None)
                session.pop("user_email", None)
                sb = new_client()
        g.sb = sb
    return g.sb


def current_user_id():
    get_sb()
    return g.get("user_id")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def with_image_urls(rows):
    """기록 목록에 비공개 사진의 서명 URL(image_url)을 붙여 반환."""
    paths = [r["image"] for r in rows if r.get("image")]
    urls = {}
    if paths:
        for item in get_sb().storage.from_(BUCKET).create_signed_urls(paths, SIGNED_URL_TTL):
            if not item.get("error"):
                urls[item["path"]] = item["signedURL"]
    for r in rows:
        r["image_url"] = urls.get(r.get("image"))
    return rows


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
    today = today_local()
    return {
        "MOODS": MOODS,
        "today": today.isoformat(),
        "today_label": today.strftime("%d %b %Y").upper(),  # 05 NOV 2026
        "quote": random.choice(QUOTES),
        "today_sunset": sunset_time(today),
    }


# ---------- 이미지 처리 ----------
def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "gif": "image/gif", "webp": "image/webp"}


def save_image(file_storage, user_id):
    """EXIF 회전 보정 + 리사이즈 후 Storage(photos/<user_id>/)에 업로드. 저장 경로 반환."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed(file_storage.filename):
        raise ValueError("지원하지 않는 이미지 형식이에요 (png/jpg/gif/webp).")

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    path = f"{user_id}/{uuid4().hex}.{ext}"

    img = Image.open(file_storage.stream)
    img = ImageOps.exif_transpose(img)  # 세로 사진 회전 보정
    img.thumbnail((THUMB_MAX, THUMB_MAX))
    if ext in ("jpg", "jpeg"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format=Image.registered_extensions()[f".{ext}"])

    get_sb().storage.from_(BUCKET).upload(
        path, buf.getvalue(), {"content-type": CONTENT_TYPES[ext]}
    )
    return path


# ---------- 인증 ----------
def _safe_next(target):
    # 외부 사이트로 튕기는 오픈 리다이렉트 방지
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("index")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if len(password) < 6:
            flash("비밀번호는 6자 이상이어야 해요.")
            return redirect(url_for("signup"))
        try:
            res = new_client().auth.sign_up({"email": email, "password": password})
        except AuthApiError as e:
            flash(f"가입하지 못했어요: {e.message}")
            return redirect(url_for("signup"))
        if res.session:  # 이메일 인증이 꺼져 있으면 바로 로그인
            session["sb_tokens"] = {"access": res.session.access_token,
                                    "refresh": res.session.refresh_token}
            flash("환영해요. 오늘의 한 컷을 남겨보세요")
            return redirect(url_for("index"))
        flash("인증 메일을 보냈어요. 메일의 링크를 누른 뒤 로그인해 주세요.")
        return redirect(url_for("login"))
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        try:
            res = new_client().auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError as e:
            if e.code == "email_not_confirmed":
                flash("아직 이메일 인증 전이에요. 메일함(스팸함 포함)의 인증 링크를 눌러주세요.")
            elif e.code == "invalid_credentials":
                flash("이메일 또는 비밀번호가 맞지 않아요.")
            else:
                app.logger.warning("login failed: %s %s", e.code, e.message)
                flash(f"로그인하지 못했어요: {e.message}")
            return redirect(url_for("login", next=request.args.get("next")))
        session.clear()
        session["sb_tokens"] = {"access": res.session.access_token,
                                "refresh": res.session.refresh_token}
        return redirect(_safe_next(request.args.get("next")))
    return render_template("auth.html", mode="login")


@app.route("/logout", methods=["POST"])
def logout():
    sb = get_sb()
    if g.get("user_id"):
        try:
            sb.auth.sign_out()
        except AuthError:
            pass
    session.clear()
    flash("로그아웃했어요.")
    return redirect(url_for("login"))


# ---------- 라우트 ----------
def fetch_entries(mood_filter=None):
    q = get_sb().table("entries").select("*")
    if mood_filter in MOODS:
        q = q.eq("mood", mood_filter)
    rows = q.order("entry_date", desc=True).order("id", desc=True).execute().data
    return with_sunsets(with_image_urls(rows))


def fetch_entry(entry_id):
    # RLS 덕분에 남의 기록은 조회 결과가 비어 있음 → 404
    rows = get_sb().table("entries").select("*").eq("id", entry_id).execute().data
    if not rows:
        abort(404)
    return rows[0]


@app.route("/")
@login_required
def index():
    mood_filter = request.args.get("mood")
    return render_template("index.html", entries=fetch_entries(mood_filter), active_mood=mood_filter)


@app.route("/archive")
@login_required
def archive():
    mood_filter = request.args.get("mood")
    return render_template("archive.html", entries=fetch_entries(mood_filter), active_mood=mood_filter)


def insert_entry(row, extras):
    """기록 저장. 부가 칸(위치·시 이름)이 아직 DB에 없으면 그 칸만 빼고 저장해서
    마이그레이션 SQL 실행 전에도 기록 자체는 막히지 않게 함."""
    extras = dict(extras)
    while True:
        try:
            return get_sb().table("entries").insert({**row, **extras}).execute()
        except APIError as e:
            # PGRST204: Could not find the '<col>' column of 'entries'
            missing = re.search(r"'(\w+)' column", e.message or "")
            if e.code == "PGRST204" and missing and missing.group(1) in extras:
                app.logger.warning("column %s missing — run supabase/*.sql; saving without it",
                                   missing.group(1))
                extras.pop(missing.group(1))
                continue
            raise


@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "GET":
        return render_template("new.html")

    # 기록하기 버튼은 노을 애니메이션을 띄운 채 fetch 로 보냄 → JSON 으로 응답
    wants_json = request.headers.get("X-Afterglow-Async") == "1"

    def fail(msg, status=400):
        if wants_json:
            return jsonify(ok=False, error=msg), status
        flash(msg)
        return redirect(url_for("new"))

    entry_date = request.form.get("entry_date", "").strip() or today_local().isoformat()
    mood = request.form.get("mood", "").strip()
    note = request.form.get("note", "").strip()

    try:
        date.fromisoformat(entry_date)
    except ValueError:
        return fail("날짜 형식이 올바르지 않아요.")
    if mood not in MOODS:
        return fail("오늘의 무드를 골라주세요.")

    try:
        image = save_image(request.files.get("image"), current_user_id())
    except ValueError as e:
        return fail(str(e))
    except UnidentifiedImageError:
        return fail("사진을 읽지 못했어요. 다른 사진으로 시도해 주세요.")
    except Exception:
        app.logger.exception("photo upload failed")
        return fail("사진을 올리지 못했어요. 잠시 후 다시 시도해 주세요.", 502)

    lat, lon, tz = parse_location(request.form)
    row = {"entry_date": entry_date, "mood": mood, "note": note, "image": image}
    extras = {"lat": lat, "lon": lon, "tz": tz,
              "place": reverse_place(lat, lon) if lat is not None else None}
    try:
        insert_entry(row, extras)  # user_id 는 DB 기본값 auth.uid() 로 채워짐
    except Exception:
        app.logger.exception("entry insert failed")
        if image:  # 기록이 안 남았으면 올린 사진도 정리
            try:
                get_sb().storage.from_(BUCKET).remove([image])
            except Exception:
                pass
        return fail("기록을 저장하지 못했어요. 잠시 후 다시 시도해 주세요.", 502)

    flash("오늘의 한 컷이 기록됐어요")
    if wants_json:
        return jsonify(ok=True, redirect=url_for("index"))
    return redirect(url_for("index"))


@app.route("/place")
@login_required
def place_name():
    """기록 쓰기 화면에서 📍 버튼을 누르면 시 이름을 미리 보여주기 위한 조회."""
    lat, lon, _ = parse_location(request.args)
    if lat is None:
        return jsonify(place=None), 400
    return jsonify(place=reverse_place(lat, lon))


@app.route("/entry/<int:entry_id>")
@login_required
def detail(entry_id):
    e = fetch_entry(entry_id)
    if e.get("lat") is not None and not e.get("place"):
        # 시 이름이 없는 예전 기록은 처음 볼 때 한 번 채워 넣음
        place = reverse_place(e["lat"], e["lon"])
        if place:
            try:
                get_sb().table("entries").update({"place": place}).eq("id", entry_id).execute()
                e["place"] = place
            except Exception:
                app.logger.exception("place backfill failed")
    e = with_sunsets(with_image_urls([e]))[0]
    return render_template("detail.html", e=e)


@app.route("/entry/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete(entry_id):
    row = fetch_entry(entry_id)
    sb = get_sb()
    sb.table("entries").delete().eq("id", entry_id).execute()
    if row["image"]:
        try:
            sb.storage.from_(BUCKET).remove([row["image"]])
        except Exception:
            pass  # 사진 삭제 실패해도 기록 삭제는 유지
    flash("기록을 지웠어요.")
    return redirect(url_for("index"))


@app.route("/calendar")
@login_required
def calendar_view():
    today = today_local()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    if not (1 <= month <= 12 and 1 <= year <= 9998):
        abort(404)

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    rows = (
        get_sb().table("entries").select("*")
        .gte("entry_date", f"{year:04d}-{month:02d}-01")
        .lt("entry_date", f"{next_year:04d}-{next_month:02d}-01")
        .order("id", desc=True)
        .execute().data
    )

    # 날짜(일) -> 대표 기록(그 달 최신) 매핑
    by_day = {}
    for r in rows:
        by_day.setdefault(int(r["entry_date"][8:10]), r)
    with_image_urls(list(by_day.values()))

    weeks = cal.Calendar(firstweekday=6).monthdayscalendar(year, month)  # 일요일 시작

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
    # 배포 시 모든 인터페이스(0.0.0.0)로 공개 → 공용 IP로 접속 가능
    # macOS 로컬은 5000번을 AirPlay가 점유하므로 8000번 사용
    # 로컬 개발에서 자동 리로드가 필요하면 FLASK_DEBUG=1 로 실행
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
