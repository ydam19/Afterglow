# 🎞️ Afterglow — 하루의 여운

하루 한 장의 사진 + 한 줄 감정 기록을 **필름/폴라로이드 감성**으로 아카이빙하고,
그날의 기분을 **감정별 색 캘린더**로 시각화하는 미니 웹앱.
필름 사진의 잔상처럼, 하루의 여운을 남겨두는 공간이에요.
모든 글씨는 만년필 손글씨 폰트(Nanum Pen Script)로 표현됩니다.

## 기능
- 📷 사진 업로드 + 한 줄 일기 + 그날의 무드 선택
- 🖼️ 폴라로이드 그리드 아카이브 (무드별 필터)
- 🗓️ 감정별 색으로 칠해지는 무드 캘린더 (월 이동)
- 🔍 기록 상세 보기 / 삭제

## 기술 스택
- **Flask** (웹 프레임워크)
- **SQLite** (내장 DB, 별도 설치 불필요)
- **Pillow** (이미지 EXIF 회전 보정 + 리사이즈)

## 실행 방법
```bash
cd film-mood-diary
python3 -m venv venv && source venv/bin/activate   # (선택) 가상환경
pip install -r requirements.txt
python app.py
```
브라우저에서 http://127.0.0.1:8000 접속.
> macOS는 5000번 포트를 AirPlay 수신 기능이 점유(HTTP 403)하므로 8000번을 사용합니다.
> AirPlay 수신을 끄고 5000번을 쓰려면: 시스템 설정 → 일반 → AirDrop 및 Handoff → "AirPlay 수신기" 끄기.

## 폴더 구조
```
film-mood-diary/
├── app.py              # Flask 앱 + 라우트 + DB/이미지 처리
├── requirements.txt
├── diary.db            # 실행 시 자동 생성 (SQLite)
├── templates/          # Jinja2 템플릿
│   ├── base.html
│   ├── index.html      # 아카이브 그리드
│   ├── new.html        # 기록 작성
│   ├── detail.html     # 상세 보기
│   ├── calendar.html   # 무드 캘린더
│   └── 404.html
└── static/
    ├── css/style.css   # 만년필 손글씨 + 필름 감성 스타일
    └── uploads/        # 업로드된 사진 저장
```
