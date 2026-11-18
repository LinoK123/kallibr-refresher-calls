-- Staff actions (spec 5.4, 5.6, 5.7, 5.10). Staff never write tables directly; every change goes
-- through these functions, which check who is calling. card_events.staff_id is the person the
-- event is about: the claimer, the new owner for 'assigned', the previous owner for 'released'.

create function claim_card(p_card_key text) returns boolean
language plpgsql security definer set search_path = public as $$
declare me uuid := current_staff_id();
begin
  if me is null then raise exception 'not staff' using errcode = '42501'; end if;
  -- One statement: if two people click at once, the second waits for the first and then finds it taken.
  update cards set claimed_by = me, claimed_at = now(), last_activity_at = now()
   where card_key = p_card_key and claimed_by is null and not do_not_call;
  if not found then return false; end if;
  insert into card_events (card_key, staff_id, event) values (p_card_key, me, 'claimed');
  return true;
end;
$$;

create function release_card(p_card_key text) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := current_staff_id(); owner uuid;
begin
  if me is null then raise exception 'not staff' using errcode = '42501'; end if;
  select claimed_by into owner from cards where card_key = p_card_key for update;
  if not found then raise exception 'card not found'; end if;
  if owner is null then return; end if;
  if owner <> me and not is_manager() then raise exception 'card not claimed by you'; end if;
  update cards set claimed_by = null, claimed_at = null where card_key = p_card_key;
  insert into card_events (card_key, staff_id, event) values (p_card_key, owner, 'released');
end;
$$;

create function assign_card(p_card_key text, p_staff_id uuid) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := current_staff_id(); c cards%rowtype;
begin
  if me is null then raise exception 'not staff' using errcode = '42501'; end if;
  if not is_manager() then raise exception 'managers only' using errcode = '42501'; end if;
  select * into c from cards where card_key = p_card_key for update;
  if not found then raise exception 'card not found'; end if;
  if p_staff_id is not null then
    if not exists (select 1 from staff where id = p_staff_id and active) then
      raise exception 'no active team member with that id';
    end if;
    if c.do_not_call then raise exception 'this card is marked do not call'; end if;
  end if;
  update cards
     set claimed_by = p_staff_id,
         claimed_at = case when p_staff_id is null then null else now() end,
         last_activity_at = now()
   where card_key = p_card_key;
  if p_staff_id is null then
    if c.claimed_by is not null then
      insert into card_events (card_key, staff_id, event) values (p_card_key, c.claimed_by, 'released');
    end if;
  else
    insert into card_events (card_key, staff_id, event) values (p_card_key, p_staff_id, 'assigned');
  end if;
end;
$$;

create function save_call_log(p_card_key text, p_notes text, p_callback_on date, p_outcomes jsonb,
                              p_dnc_card boolean default false) returns jsonb
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

  -- 4. The call, then each line's outcome. A line that became Won since the page loaded keeps its win.
  insert into call_logs (card_key, staff_id, notes, callback_on)
  values (p_card_key, me, p_notes, p_callback_on) returning id into log_id;

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

create function clear_do_not_call(p_card_key text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if current_staff_id() is null then raise exception 'not staff' using errcode = '42501'; end if;
  if not is_manager() then raise exception 'managers only' using errcode = '42501'; end if;
  update cards set do_not_call = false where card_key = p_card_key;
  if not found then raise exception 'card not found'; end if;
  update lines l
     set status = 'not_called', outcome = null, last_outcome_by = null, last_outcome_at = null
    from students s
   where s.contact_id = l.contact_id and s.card_key = p_card_key
     and l.status = 'lost' and l.outcome = 'do_not_call';
end;
$$;

create function upsert_staff(p_email text, p_full_name text, p_role text, p_active boolean) returns uuid
language plpgsql security definer set search_path = public as $$
declare me uuid := current_staff_id(); v_email text := lower(trim(p_email)); v_id uuid; r record;
begin
  if me is null then raise exception 'not staff' using errcode = '42501'; end if;
  if not is_manager() then raise exception 'managers only' using errcode = '42501'; end if;
  if v_email is null or v_email !~ '^[^@\s]+@[^@\s]+$' then raise exception 'enter a valid email address'; end if;
  if coalesce(trim(p_full_name), '') = '' then raise exception 'enter a name'; end if;
  if v_email = (select email from staff where id = me) and (not p_active or p_role <> 'manager') then
    raise exception 'you can''t remove your own manager access';
  end if;

  insert into staff (email, full_name, role, active) values (v_email, trim(p_full_name), p_role, p_active)
  on conflict (email) do update
     set full_name = excluded.full_name, role = excluded.role, active = excluded.active
  returning id into v_id;

  if not p_active then
    for r in select card_key from cards where claimed_by = v_id for update loop
      update cards set claimed_by = null, claimed_at = null where card_key = r.card_key;
      insert into card_events (card_key, staff_id, event) values (r.card_key, v_id, 'released');
    end loop;
  end if;
  return v_id;
end;
$$;

revoke execute on function claim_card(text), release_card(text), assign_card(text, uuid),
  save_call_log(text, text, date, jsonb, boolean), clear_do_not_call(text),
  upsert_staff(text, text, text, boolean)
  from public, anon, authenticated, service_role;
grant execute on function claim_card(text), release_card(text), assign_card(text, uuid),
  save_call_log(text, text, date, jsonb, boolean), clear_do_not_call(text),
  upsert_staff(text, text, text, boolean)
  to authenticated;
