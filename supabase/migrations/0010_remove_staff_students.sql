-- One-off clean-up (owner's request, 23 Nov 2026): Kallibr staff are not students.
-- The nightly push stopped listing them (design 2026-11-23-staff-not-students); this removes the ones already
-- in the tool. Staff students are picked by the same organisation rule as push/config.py STAFF_ORG_PREFIXES,
-- applied to students.org_name, so no names or contact IDs are written here.
-- Removes their outcomes, refreshers, course history and student rows, then releases any held card left with
-- no students. Call logs and card rows stay. On a database with no staff students it changes nothing.

do $$
declare
  v_ids      bigint[];
  v_cards    text[];
  n_students int;
  n_lines    int;
  n_outcomes int;
  n_history  int;
  n_released int;
begin
  select coalesce(array_agg(contact_id), '{}'), coalesce(array_agg(distinct card_key), '{}')
    into v_ids, v_cards
    from students
   where lower(trim(org_name)) like 'kallibr%' or lower(trim(org_name)) like 'gl training%';
  n_students := cardinality(v_ids);

  -- Guard: 11 refreshers were expected on 23 Nov 2026. Far more means the rule is catching customers.
  select count(*) into n_lines from lines where contact_id = any(v_ids);
  if n_lines > 20 then
    raise exception 'refusing: % refreshers would be removed (no more than 20 expected); nothing changed', n_lines;
  end if;

  delete from line_outcomes where line_id in (select id from lines where contact_id = any(v_ids));
  get diagnostics n_outcomes = row_count;
  delete from lines where contact_id = any(v_ids);
  delete from course_history where contact_id = any(v_ids);
  get diagnostics n_history = row_count;
  delete from students where contact_id = any(v_ids);

  -- A held card left with no students goes back, with a 'released' event naming who held it.
  with old as (
    select c.card_key, c.claimed_by from cards c
     where c.card_key = any(v_cards) and c.claimed_by is not null
       and not exists (select 1 from students s where s.card_key = c.card_key)
       for update
  ), rel as (
    update cards c set claimed_by = null, claimed_at = null, callback_on = null
      from old where c.card_key = old.card_key
    returning old.card_key, old.claimed_by
  )
  insert into card_events (card_key, staff_id, event)
  select card_key, claimed_by, 'released' from rel;
  get diagnostics n_released = row_count;

  raise notice 'staff students removed: % students, % refreshers, % outcomes, % history rows, % cards released',
    n_students, n_lines, n_outcomes, n_history, n_released;
end;
$$;
