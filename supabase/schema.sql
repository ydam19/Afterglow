-- Afterglow — Supabase 스키마
-- Supabase 대시보드 → SQL Editor 에 통째로 붙여넣고 Run.
-- 여러 번 실행해도 안전하도록 작성됨.

-- ========== 기록 테이블 ==========
create table if not exists public.entries (
    id          bigint generated always as identity primary key,
    user_id     uuid not null default auth.uid()
                references auth.users (id) on delete cascade,
    entry_date  date not null,
    mood        text not null,
    note        text not null default '',
    image       text,                       -- Storage 경로: <user_id>/<파일명>
    lat         double precision check (lat between -90 and 90),    -- 노을 계산용 위치 (없으면 서울)
    lon         double precision check (lon between -180 and 180),
    tz          text,                                               -- IANA 시간대
    place       text,                                               -- 시 이름 (예: 성남시)
    created_at  timestamptz not null default now()
);

-- 이미 만들어진 테이블에도 위치 칸 추가 (002_sunset_location.sql 과 동일)
alter table public.entries
    add column if not exists lat double precision check (lat between -90 and 90),
    add column if not exists lon double precision check (lon between -180 and 180),
    add column if not exists tz  text,
    add column if not exists place text;

create index if not exists entries_user_date_idx
    on public.entries (user_id, entry_date desc, id desc);

-- ========== Data API 권한 ==========
-- 'Automatically expose new tables' 를 끈 프로젝트 기준: 로그인 사용자에게만 명시적으로 허용.
-- (anon 에는 아무 권한도 주지 않음 → 로그인 안 하면 테이블 자체에 접근 불가)
revoke all on public.entries from anon;
grant select, insert, update, delete on public.entries to authenticated;

-- ========== RLS: 본인 기록만 읽기/쓰기/삭제 ==========
alter table public.entries enable row level security;

drop policy if exists "entries_select_own" on public.entries;
create policy "entries_select_own" on public.entries
    for select to authenticated
    using ((select auth.uid()) = user_id);

drop policy if exists "entries_insert_own" on public.entries;
create policy "entries_insert_own" on public.entries
    for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "entries_update_own" on public.entries;
create policy "entries_update_own" on public.entries
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

drop policy if exists "entries_delete_own" on public.entries;
create policy "entries_delete_own" on public.entries
    for delete to authenticated
    using ((select auth.uid()) = user_id);

-- ========== 사진 저장소 (비공개 버킷) ==========
insert into storage.buckets (id, name, public)
values ('photos', 'photos', false)
on conflict (id) do nothing;

-- 사진은 photos/<user_id>/... 경로에만, 본인 폴더만 접근 가능
drop policy if exists "photos_select_own" on storage.objects;
create policy "photos_select_own" on storage.objects
    for select to authenticated
    using (bucket_id = 'photos'
           and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "photos_insert_own" on storage.objects;
create policy "photos_insert_own" on storage.objects
    for insert to authenticated
    with check (bucket_id = 'photos'
                and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "photos_delete_own" on storage.objects;
create policy "photos_delete_own" on storage.objects
    for delete to authenticated
    using (bucket_id = 'photos'
           and (storage.foldername(name))[1] = (select auth.uid())::text);
