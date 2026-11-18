-- Access rules (spec 5.10). Nothing is readable without a signed-in, active staff account.
-- Staff write only through the security-definer functions in 0003; only the nightly push
-- (service role) writes lines, cards, course history and win data.

-- Status a staff outcome puts a line in. Won is never a staff outcome.
create function outcome_status(p_outcome text) returns text
language plpgsql immutable as $$
declare s text;
begin
  s := case p_outcome
    when 'no_answer' then 'pending' when 'call_back' then 'pending'
    when 'info_sent' then 'pending' when 'will_book' then 'pending'
    when 'not_needed' then 'lost' when 'went_elsewhere' then 'lost'
    when 'left_company' then 'lost' when 'do_not_call' then 'lost'
  end;
  if s is null then
    raise exception 'unknown outcome: %', p_outcome using errcode = '22023';
  end if;
  return s;
end;
$$;

create function sydney_today() returns date
language sql stable as $$
  select (now() at time zone 'Australia/Sydney')::date
$$;

-- The caller's staff ID: active staff row whose email matches the JWT's email claim.
create function current_staff_id() returns uuid
language sql stable security definer set search_path = public as $$
  select s.id from public.staff s
  where s.email = lower(auth.jwt() ->> 'email') and s.active
$$;

create function is_staff() returns boolean
language sql stable set search_path = public as $$
  select public.current_staff_id() is not null
$$;

create function is_manager() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.staff s where s.id = public.current_staff_id() and s.role = 'manager')
$$;

-- ---------- grants: explicit, whatever the project's defaults ----------
revoke all on all tables in schema public from anon, authenticated, service_role, public;
revoke all on all sequences in schema public from anon, authenticated, service_role, public;

grant select on staff, cards, students, lines, course_history, call_logs, line_outcomes, card_events, sync_runs
  to authenticated;

grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke execute on function outcome_status(text), sydney_today(), current_staff_id(), is_staff(), is_manager()
  from public, anon, authenticated, service_role;
grant execute on function outcome_status(text), sydney_today(), current_staff_id(), is_staff(), is_manager()
  to authenticated, service_role;

-- ---------- row-level security ----------
alter table staff enable row level security;
alter table cards enable row level security;
alter table students enable row level security;
alter table lines enable row level security;
alter table course_history enable row level security;
alter table call_logs enable row level security;
alter table line_outcomes enable row level security;
alter table card_events enable row level security;
alter table sync_runs enable row level security;
alter table stage_students enable row level security;
alter table stage_lines enable row level security;
alter table stage_checks enable row level security;
alter table stage_history enable row level security;

create policy staff_read on staff for select to authenticated using ((select is_staff()));
create policy staff_read on cards for select to authenticated using ((select is_staff()));
create policy staff_read on students for select to authenticated using ((select is_staff()));
create policy staff_read on lines for select to authenticated using ((select is_staff()));
create policy staff_read on course_history for select to authenticated using ((select is_staff()));
create policy staff_read on call_logs for select to authenticated using ((select is_staff()));
create policy staff_read on line_outcomes for select to authenticated using ((select is_staff()));
create policy staff_read on card_events for select to authenticated using ((select is_staff()));
create policy staff_read on sync_runs for select to authenticated using ((select is_staff()));
-- No policies on stage_* tables; no insert/update/delete policies anywhere.
