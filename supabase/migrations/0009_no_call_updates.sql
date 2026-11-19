-- Updates saved with no call (owner's request, 20 Nov 2026), for example an outcome from an email reply.
-- call_logs.no_call marks them. They set outcomes the same way, count as working the card (cards taken, win
-- credit) and show in the card's history, but they don't count as calls logged.

alter table call_logs add column no_call boolean not null default false;

-- save_call_log gains p_no_call. It defaults to false, so a page that doesn't send it still logs a call.
-- Otherwise the body is unchanged from 0003.
drop function save_call_log(text, text, date, jsonb, boolean);

create function save_call_log(p_card_key text, p_notes text, p_callback_on date, p_outcomes jsonb,
                              p_dnc_card boolean default false, p_no_call boolean default false) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  me uuid := current_staff_id();
  c cards%rowtype;
  o record;
  cur_status text;
  log_id bigint;
  skipped bigint[] := '{}';
begin
  if me is null then raise exception 'not staff' using errcode = '42501'; end if;

  -- 1. Owner or manager.
  select * into c from cards where card_key = p_card_key for update;
  if not found then raise exception 'card not found'; end if;
  if c.claimed_by is distinct from me and not is_manager() then
    raise exception 'card not claimed by you';
  end if;

  -- 2. At least one outcome; every line on this card; every outcome known.
  if p_outcomes is null or jsonb_typeof(p_outcomes) <> 'array' or jsonb_array_length(p_outcomes) = 0 then
    raise exception 'choose an outcome for at least one refresher';
  end if;
  for o in select (e ->> 'line_id')::bigint as line_id, e ->> 'outcome' as outcome
             from jsonb_array_elements(p_outcomes) e loop
    if o.line_id is null or not exists (
         select 1 from lines l join students s on s.contact_id = l.contact_id
          where l.id = o.line_id and s.card_key = p_card_key) then
      raise exception 'line not on this card';
    end if;
    perform outcome_status(o.outcome);
  end loop;

  -- 3. A call-back needs a date, today or later (Sydney).
  if (p_callback_on is not null and p_callback_on < sydney_today())
     or (p_callback_on is null and exists (select 1 from jsonb_array_elements(p_outcomes) e
                                            where e ->> 'outcome' = 'call_back')) then
    raise exception 'call-back date required (today or later)';
  end if;

  -- 4. The call (or update with no call), then each line's outcome. A line that became Won since the page
  --    loaded keeps its win.
  insert into call_logs (card_key, staff_id, notes, callback_on, no_call)
  values (p_card_key, me, p_notes, p_callback_on, coalesce(p_no_call, false)) returning id into log_id;

  for o in select (e ->> 'line_id')::bigint as line_id, e ->> 'outcome' as outcome
             from jsonb_array_elements(p_outcomes) e loop
    select status into cur_status from lines where id = o.line_id for update;
    if cur_status = 'won' then
      skipped := skipped || o.line_id;
      continue;
    end if;
    insert into line_outcomes (call_log_id, line_id, outcome) values (log_id, o.line_id, o.outcome);
    update lines
       set status = outcome_status(o.outcome), outcome = o.outcome,
           last_outcome_by = me, last_outcome_at = now()
     where id = o.line_id;
  end loop;

  -- 5. Card activity.
  update cards set callback_on = p_callback_on, last_activity_at = now() where card_key = p_card_key;

  -- 6. Do not call, whole card.
  if p_dnc_card then
    insert into line_outcomes (call_log_id, line_id, outcome)
    select log_id, l.id, 'do_not_call'
      from lines l join students s on s.contact_id = l.contact_id
     where s.card_key = p_card_key and l.status in ('not_called', 'pending');
    update lines l
       set status = 'lost', outcome = 'do_not_call', last_outcome_by = me, last_outcome_at = now()
      from students s
     where s.contact_id = l.contact_id and s.card_key = p_card_key and l.status in ('not_called', 'pending');
    update cards set do_not_call = true, claimed_by = null, claimed_at = null, callback_on = null
     where card_key = p_card_key;
    if c.claimed_by is not null then
      insert into card_events (card_key, staff_id, event) values (p_card_key, c.claimed_by, 'released');
    end if;
  end if;

  return jsonb_build_object('call_log_id', log_id, 'skipped_line_ids', to_jsonb(skipped));
end;
$$;

revoke execute on function save_call_log(text, text, date, jsonb, boolean, boolean)
  from public, anon, authenticated, service_role;
grant execute on function save_call_log(text, text, date, jsonb, boolean, boolean) to authenticated;

-- team_stats: calls logged counts calls only. Otherwise unchanged from 0007; an update with no call still
-- counts as working a card for cards taken.
create or replace function team_stats(p_from date default null)
returns table(staff_id uuid, full_name text, cards_taken int, calls_logged int, pending int, won int, lost int,
              win_rate numeric)
language plpgsql stable security definer set search_path = public as $$
#variable_conflict use_column
begin
  if not is_staff() then raise exception 'not staff' using errcode = '42501'; end if;
  return query
  with t as (
    select s.id as sid, s.full_name as sname,
      (select count(distinct e.card_key) from card_events e
        where e.staff_id = s.id and e.event in ('claimed', 'assigned')
          and (p_from is null or (e.at at time zone 'Australia/Sydney')::date >= p_from)
          -- still theirs, or they logged a call or update on it after taking it: a take released with
          -- nothing logged is a mis-click
          and (exists (select 1 from cards c where c.card_key = e.card_key and c.claimed_by = s.id)
               or exists (select 1 from call_logs cl
                           where cl.card_key = e.card_key and cl.staff_id = s.id and cl.called_at >= e.at)))::int as taken,
      (select count(*) from call_logs cl
        where cl.staff_id = s.id and not cl.no_call
          and (p_from is null or (cl.called_at at time zone 'Australia/Sydney')::date >= p_from))::int as calls,
      (select count(*) from lines l
        where l.status = 'pending' and l.last_outcome_by = s.id
          and (p_from is null or (l.last_outcome_at at time zone 'Australia/Sydney')::date >= p_from))::int as pend,
      (select count(*) from lines l
        where l.status = 'won' and l.won_by = s.id
          and (p_from is null or l.won_at >= p_from))::int as wins,
      (select count(*) from lines l
        where l.status = 'lost' and l.last_outcome_by = s.id
          and (p_from is null or (l.last_outcome_at at time zone 'Australia/Sydney')::date >= p_from))::int as losses
    from staff s
    where s.active
  )
  select sid, sname, taken, calls, pend, wins, losses,
         round(wins::numeric / nullif(wins + losses, 0), 3)
    from t
   order by sname;
end;
$$;

revoke execute on function team_stats(date) from public, anon, authenticated, service_role;
grant execute on function team_stats(date) to authenticated;
