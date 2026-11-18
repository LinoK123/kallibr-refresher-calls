-- Kallibr Refresher Call Tool: tables (spec 5.9). No phone numbers, emails (other than staff
-- sign-in), addresses, dates of birth, USIs, payment or invoice details are ever stored.

create table staff (
  id         uuid primary key default gen_random_uuid(),
  email      text unique not null check (email = lower(email)),
  full_name  text not null,
  role       text not null check (role in ('staff', 'manager')),
  active     boolean not null default true
);

create table cards (
  card_key           text primary key,                -- B:<booker id> | O:<org key> | S:<student id>
  kind               text not null check (kind in ('booker', 'organisation', 'individual')),
  target_contact_id  bigint,
  target_name        text not null,
  org_name           text,
  org_key            text,
  claimed_by         uuid references staff,
  claimed_at         timestamptz,
  last_activity_at   timestamptz,
  callback_on        date,
  do_not_call        boolean not null default false
);

create table students (
  contact_id  bigint primary key,
  full_name   text not null,
  org_name    text,
  card_key    text not null references cards
);

create table lines (
  id                    bigserial primary key,
  contact_id            bigint not null references students,
  refresher_type        text not null check (refresher_type in ('Confined Space', 'Heights', 'HSR')),
  last_done             date not null,
  due_date              date not null,
  course_name           text,
  location              text,
  attendance_confirmed  boolean not null default true,
  in_window             boolean not null default true,
  tentative             boolean not null default false,
  first_listed_on       date not null,
  status                text not null default 'not_called'
                        check (status in ('not_called', 'pending', 'won', 'lost')),
  outcome               text,
  last_outcome_by       uuid references staff,
  last_outcome_at       timestamptz,
  status_before_won     text,
  outcome_before_won    text,
  won_at                date,
  won_booked_on         date,
  won_class_date        date,
  won_course            text,
  won_by                uuid references staff,
  won_without_call      boolean,
  unique (contact_id, refresher_type, last_done)
);

create table course_history (
  contact_id    bigint,
  course_name   text,
  completed_on  date,
  primary key (contact_id, course_name, completed_on)
);

create table call_logs (
  id           bigserial primary key,
  card_key     text not null references cards,
  staff_id     uuid not null references staff,
  called_at    timestamptz not null default now(),
  notes        text,
  callback_on  date
);

create table line_outcomes (
  id           bigserial primary key,
  call_log_id  bigint not null references call_logs,
  line_id      bigint not null references lines,
  outcome      text not null
);

create table card_events (
  id        bigserial primary key,
  card_key  text not null,
  staff_id  uuid,
  event     text not null check (event in ('claimed', 'released', 'assigned', 'auto_released')),
  at        timestamptz not null default now()
);

create table sync_runs (
  id                bigserial primary key,
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  source_synced_at  timestamptz,
  result            text not null default 'running' check (result in ('running', 'ok', 'aborted', 'failed')),
  message           text,
  lines_pushed      int,
  students_pushed   int,
  checks_pushed     int,
  history_pushed    int,
  wins              int,
  reversals         int
);

-- Staging: filled by the nightly push, merged by apply_push, then emptied.
create table stage_students (
  run_id bigint, contact_id bigint, full_name text, org_name text, card_key text, card_kind text,
  target_contact_id bigint, target_name text, card_org_name text, card_org_key text
);
create table stage_lines (
  run_id bigint, contact_id bigint, refresher_type text, last_done date, due_date date, course_name text,
  location text, attendance_confirmed boolean
);
create table stage_checks (
  run_id bigint, contact_id bigint, refresher_type text, last_done date, in_window boolean, won boolean,
  booked_on date, class_date date, course_name text, tentative boolean
);
create table stage_history (
  run_id bigint, contact_id bigint, course_name text, completed_on date
);

create index students_card_key on students (card_key);
create index lines_contact_id on lines (contact_id);
create index lines_status on lines (status);
create index call_logs_card_key on call_logs (card_key);
create index line_outcomes_line_id on line_outcomes (line_id);
create index cards_org_key on cards (org_key);
create index cards_claimed_by on cards (claimed_by);
create index stage_students_run on stage_students (run_id);
create index stage_lines_run on stage_lines (run_id);
create index stage_checks_run on stage_checks (run_id);
create index stage_history_run on stage_history (run_id);
