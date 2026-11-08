-- 003: 노을을 본 곳의 시 이름 (예: 서울, 성남시, 파리)
-- Supabase SQL Editor 에서 한 번 실행. 여러 번 실행해도 안전.
alter table public.entries
    add column if not exists place text;
