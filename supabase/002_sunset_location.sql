-- 002: 기록마다 노을(일몰) 시각을 계산하기 위한 위치 정보
-- Supabase SQL Editor 에서 한 번 실행. 여러 번 실행해도 안전.
alter table public.entries
    add column if not exists lat double precision
        check (lat between -90 and 90),
    add column if not exists lon double precision
        check (lon between -180 and 180),
    add column if not exists tz  text;          -- IANA 시간대 (예: Asia/Seoul)
