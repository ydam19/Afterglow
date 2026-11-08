# 🎞️ Afterglow — 하루의 여운

하루 한 장의 사진 + 한 줄 감정 기록을 **필름/폴라로이드 감성**으로 아카이빙하고,
그날의 기분을 **감정별 캘린더**로 모아 보는 미니 웹앱.
필름 사진의 잔상처럼, 하루의 여운을 남겨두는 공간이에요.

## 기능
- 🔐 이메일 가입·로그인 — **내 기록은 나만** 볼 수 있어요
- 📷 사진 업로드 + 한 줄 일기 + 그날의 무드 선택
- 🌅 **그날의 노을 시각** — 기록한 곳(시 단위, 예: 성남시) 기준으로 일몰 시각 표시
  - 위치를 남기지 않으면 서울 기준
- 🌇 **기록하기 연출** — 사진 뒤로 해가 지고 "오늘이 저물었어요 / 여운으로 남겨둘게요"
- 🖼️ 폴라로이드 그리드 아카이브 (무드별 필터)
- 🗓️ 무드 캘린더 (월 이동)
- 🔍 기록 상세 보기 / 삭제

## 기술 스택
- **Flask** — 웹 프레임워크
- **Supabase** — Auth(로그인), Postgres(기록), Storage(사진)
  - 행 단위 보안(RLS)으로 본인 기록·사진만 읽고 쓸 수 있음
- **Pillow** — 사진 EXIF 회전 보정 + 리사이즈
- **astral** — 날짜·위치로 일몰 시각 계산 (외부 API 없음)
- **OpenStreetMap Nominatim** — 좌표 → 시 이름 (기록할 때 한 번만 조회)

## 시작하기

### 1. Supabase 준비
1. [supabase.com](https://supabase.com)에서 프로젝트 생성 (리전: Northeast Asia (Seoul) 권장)
2. 대시보드 → **SQL Editor** → `supabase/schema.sql` 전체를 붙여넣고 **Run**
   - 테이블, 보안 규칙(RLS), 사진 버킷(`photos`)이 한 번에 만들어져요
   - 기존 프로젝트를 업데이트할 때는 `002_…`, `003_…` 파일을 순서대로 실행

### 2. 환경 변수
```bash
cp .env.example .env
```
`.env`에 값을 채워요.

| 키 | 값 |
|---|---|
| `SUPABASE_URL` | Project URL (`https://<project-ref>.supabase.co`) |
| `SUPABASE_ANON_KEY` | **anon / publishable** 키 |
| `SECRET_KEY` | 아무 긴 랜덤 문자열 (`python3 -c "import secrets;print(secrets.token_hex(32))"`) |

> ⚠️ `service_role` / `secret` 키는 절대 넣지 마세요. RLS를 무시해서 모든 사람의 기록이 보여요.
> `.env`는 `.gitignore`에 포함되어 GitHub에 올라가지 않아요.

### 3. 실행
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```
브라우저에서 http://127.0.0.1:8000 접속 → 가입 후 로그인.

> macOS는 5000번 포트를 AirPlay 수신 기능이 점유(HTTP 403)하므로 8000번을 사용해요.
> 다른 포트: `PORT=5050 python app.py` · 자동 리로드: `FLASK_DEBUG=1 python app.py`

## 참고
- Supabase는 기본적으로 **가입 시 인증 메일**을 보내요. 메일 링크를 누른 뒤 로그인하면 돼요.
  - 로컬에서는 링크가 `localhost:3000`으로 이동해 "연결할 수 없음"이 뜨지만, 인증은 이미 완료된 상태예요.
  - 배포 후 Supabase **Authentication → URL Configuration → Site URL**을 배포 주소로 바꾸면 해결돼요.
- 📍 "지금 위치로 맞추기"는 브라우저 위치 권한이 필요하고, 휴대폰에서는 HTTPS(배포 환경)에서만 동작해요.
  - 좌표는 약 1km 단위로 반올림해 저장해요.
- 날짜는 서버 시간대와 관계없이 **한국 시간** 기준이에요.

## 폴더 구조
```
Afterglow/
├── app.py                 # Flask 앱: 인증, 라우트, Supabase·사진·노을 처리
├── requirements.txt
├── .env.example           # 환경 변수 양식 (.env 로 복사해서 사용)
├── supabase/
│   ├── schema.sql         # 처음 한 번: 테이블 + RLS + 사진 버킷
│   ├── 002_sunset_location.sql   # 위치(위도·경도·시간대) 칸 추가
│   └── 003_place_name.sql        # 시 이름 칸 추가
├── templates/             # Jinja2 템플릿
│   ├── base.html
│   ├── auth.html          # 로그인 / 가입
│   ├── index.html         # 메인 (오늘의 노을 시각)
│   ├── archive.html       # 폴라로이드 아카이브
│   ├── new.html           # 기록 작성 + 노을 연출
│   ├── detail.html        # 상세 보기 (그날의 노을 시각)
│   ├── calendar.html      # 무드 캘린더
│   └── 404.html
└── static/
    ├── css/style.css      # 필름 감성 스타일 + 노을 연출
    ├── js/app.js          # 인터랙션, 위치, 기록하기 연출
    └── img/               # 배경 사진 (window.jpg, 개인 이미지라 Git 제외)
```
