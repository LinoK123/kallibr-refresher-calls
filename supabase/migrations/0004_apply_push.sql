-- Nightly merge (spec 5.3 sticky placement, 5.4 do not call, 5.5 winning, 5.6 auto-release, 5.11).
-- Called once by the nightly push after it has filled the stage_* tables for one sync_runs row.
-- One function call is one transaction: any error leaves every live table as it was.
-- Never deletes call logs, outcomes or claims.

create function apply_push(p_run_id bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  r          sync_runs%rowtype;
  v_today    date := sydney_today();
  n_new      int := 0;
  n_wins     int := 0;
  n_rev      int := 0;
  n_released int := 0;
begin
  -- 1. The run must exist, be running, and its staging must be complete.
  select * into r from sync_runs where id = p_run_id for update;
  if not found or r.result <> 'running' then
    raise exception 'run not found or not running';
  end if;
  if (select count(*) from stage_students where run_id = p_run_id) <> coalesce(r.students_pushed, 0)
     or (select count(*) from stage_lines where run_id = p_run_id) <> coalesce(r.lines_pushed, 0)
     or (select count(*) from stage_checks where run_id = p_run_id) <> coalesce(r.checks_pushed, 0)
     or (select count(*) from stage_history where run_id = p_run_id) <> coalesce(r.history_pushed, 0) then
    raise exception 'staging incomplete';
  end if;

  -- 2. Cards: create new ones; refresh names only on existing ones (claims and flags are kept).
  insert into cards (card_key, kind, target_contact_id, target_name, org_name, org_key)
  select distinct on (card_key) card_key, card_kind, target_contact_id, target_name, card_org_name, card_org_key
    from stage_students where run_id = p_run_id
   order by card_key, contact_id
  on conflict (card_key) do update
     set target_name = excluded.target_name, org_name = excluded.org_name, org_key = excluded.org_key;

  -- 3. Students: a student with any logged outcome stays on their card (sticky placement).
  insert into students (contact_id, full_name, org_name, card_key)
  select contact_id, full_name, org_name, card_key from stage_students where run_id = p_run_id
  on conflict (contact_id) do update
     set full_name = excluded.full_name,
         org_name  = excluded.org_name,
         card_key  = case when exists (select 1 from line_outcomes lo join lines l on l.id = lo.line_id
                                        where l.contact_id = students.contact_id)
                          then students.card_key else excluded.card_key end;

  -- 4. Lines: new ones start Not called; existing ones only get their descriptive fields refreshed.
  with up as (
    insert into lines (contact_id, refresher_type, last_done, due_date, course_name, location,
                       attendance_confirmed, first_listed_on)
    select contact_id, refresher_type, last_done, due_date, course_name, location,
           coalesce(attendance_confirmed, true), v_today
      from stage_lines where run_id = p_run_id
    on conflict (contact_id, refresher_type, last_done) do update
       set due_date = excluded.due_date, course_name = excluded.course_name,
           location = excluded.location, attendance_confirmed = excluded.attendance_confirmed
    returning (xmax = 0) as inserted
  )
  select count(*) filter (where inserted) into n_new from up;

  -- Fresh statistics for what was just loaded. The staging tables are emptied every night, so
  -- their stored statistics say "zero rows"; plans built on that took 31s instead of under 1s
  -- and hit the API's 8s limit. ANALYZE counts this transaction's own uncommitted rows.
  analyze cards, students, lines, stage_checks, stage_history;

  -- 5. Do not call: a Not called line on a flagged card is lost straight away and never queued.
  update lines l
     set status = 'lost', outcome = 'do_not_call', last_outcome_by = null, last_outcome_at = null
    from students s join cards c on c.card_key = s.card_key
   where s.contact_id = l.contact_id and c.do_not_call and l.status = 'not_called';

  -- 6. Checks. Flags first.
  update lines l
     set in_window = c.in_window, tentative = coalesce(c.tentative, false)
    from stage_checks c
   where c.run_id = p_run_id and c.contact_id = l.contact_id
     and c.refresher_type = l.refresher_type and c.last_done = l.last_done;

  -- Still won: keep the win and its credit; follow a booking that moved to another class.
  update lines l
     set won_class_date = c.class_date, won_course = c.course_name
    from stage_checks c
   where c.run_id = p_run_id and c.contact_id = l.contact_id
     and c.refresher_type = l.refresher_type and c.last_done = l.last_done
     and c.won and l.status = 'won';

  -- New wins: credit the latest caller on the student's card on or before the booking date (Sydney).
  with cand as (
    select l.id, coalesce(c.booked_on, v_today) as booked_on, c.class_date, c.course_name,
           (select cl.staff_id from call_logs cl
             where cl.card_key = s.card_key
               and (cl.called_at at time zone 'Australia/Sydney')::date <= coalesce(c.booked_on, v_today)
             order by cl.called_at desc, cl.id desc
             limit 1) as caller
      from lines l
      join stage_checks c on c.run_id = p_run_id and c.contact_id = l.contact_id
                         and c.refresher_type = l.refresher_type and c.last_done = l.last_done
      join students s on s.contact_id = l.contact_id
     where c.won and l.status <> 'won'
  ), w as (
    update lines l
       set status_before_won = l.status, outcome_before_won = l.outcome, status = 'won',
           won_at = v_today, won_booked_on = cand.booked_on, won_class_date = cand.class_date,
           won_course = cand.course_name, won_by = cand.caller, won_without_call = (cand.caller is null)
      from cand
     where cand.id = l.id
    returning l.id
  )
  select count(*) into n_wins from w;

  -- Reversals: no real booking remains, so the line returns to what it was before the win.
  with rv as (
    update lines l
       set status = coalesce(l.status_before_won, 'not_called'), outcome = l.outcome_before_won,
           status_before_won = null, outcome_before_won = null,
           won_at = null, won_booked_on = null, won_class_date = null, won_course = null,
           won_by = null, won_without_call = null
      from stage_checks c
     where c.run_id = p_run_id and c.contact_id = l.contact_id
       and c.refresher_type = l.refresher_type and c.last_done = l.last_done
       and not c.won and l.status = 'won'
    returning l.id
  )
  select count(*) into n_rev from rv;

  -- 7. Auto-release: 14 days without activity and no call-back still to come.
  with old as (
    select card_key, claimed_by from cards
     where claimed_by is not null
       and coalesce(last_activity_at, claimed_at) < now() - interval '14 days'
       and (callback_on is null or callback_on < v_today)
       for update
  ), rel as (
    update cards c set claimed_by = null, claimed_at = null
      from old where c.card_key = old.card_key
    returning old.card_key, old.claimed_by
  )
  insert into card_events (card_key, staff_id, event)
  select card_key, claimed_by, 'auto_released' from rel;
  get diagnostics n_released = row_count;

  -- 8. Course history: replaced for every student in this run.
  delete from course_history h
   where h.contact_id in (select contact_id from stage_students where run_id = p_run_id
                          union select contact_id from stage_history where run_id = p_run_id);
  insert into course_history (contact_id, course_name, completed_on)
  select distinct contact_id, course_name, completed_on from stage_history
   where run_id = p_run_id and contact_id is not null and course_name is not null and completed_on is not null
  on conflict do nothing;

  -- 9. Finish the run; clear staging; anything older still running was abandoned.
  update sync_runs set finished_at = now(), result = 'ok', wins = n_wins, reversals = n_rev
   where id = p_run_id;
  delete from stage_students where run_id <= p_run_id;
  delete from stage_lines    where run_id <= p_run_id;
  delete from stage_checks   where run_id <= p_run_id;
  delete from stage_history  where run_id <= p_run_id;
  update sync_runs set result = 'failed', message = 'superseded', finished_at = now()
   where result = 'running' and id < p_run_id;

  return jsonb_build_object('lines_new', n_new, 'wins', n_wins, 'reversals', n_rev, 'released', n_released);
end;
$$;

revoke execute on function apply_push(bigint) from public, anon, authenticated, service_role;
grant execute on function apply_push(bigint) to service_role;
