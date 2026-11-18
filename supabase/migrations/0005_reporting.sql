-- Reporting for the site: the queue (v_cards), the team table (team_stats) and the cohort chart
-- (cohort_counts), spec 5.6 and 5.8. All dates on the Sydney calendar.

-- One row per card. An open line is Not called or Pending and still in the 3-year window;
-- the per-card counts cover open lines only. Read through row-level security (security_invoker).
create view v_cards with (security_invoker = true) as
with open_lines as (
  select s.card_key, l.contact_id, l.due_date, l.location, l.refresher_type, l.tentative
    from lines l
    join students s on s.contact_id = l.contact_id
   where l.status in ('not_called', 'pending') and l.in_window
), agg as (
  select card_key,
         count(distinct contact_id)::int                          as students,
         count(*)::int                                            as open_lines,
         count(*) filter (where due_date < sydney_today())::int   as overdue_lines,
         min(due_date)                                            as earliest_due,
         array_agg(distinct location) filter (where location is not null) as locations,
         array_agg(distinct refresher_type)                       as types,
         bool_or(tentative)                                       as has_tentative
    from open_lines
   group by card_key
), org_open as (
  select c.org_key, count(*)::int as n
    from cards c join agg a on a.card_key = c.card_key
   where c.org_key is not null and a.open_lines > 0
   group by c.org_key
)
select c.card_key, c.kind, c.target_contact_id, c.target_name, c.org_name, c.org_key,
       c.claimed_by, st.full_name as claimed_by_name, c.claimed_at, c.callback_on, c.do_not_call,
       coalesce(a.students, 0)          as students,
       coalesce(a.open_lines, 0)        as open_lines,
       coalesce(a.overdue_lines, 0)     as overdue_lines,
       a.earliest_due,
       coalesce(a.locations, '{}')      as locations,
       coalesce(a.types, '{}')          as types,
       coalesce(a.has_tentative, false) as has_tentative,
       (coalesce(o.n, 0) - case when coalesce(a.open_lines, 0) > 0 then 1 else 0 end)::int as sibling_cards
  from cards c
  left join agg a on a.card_key = c.card_key
  left join org_open o on o.org_key = c.org_key
  left join staff st on st.id = c.claimed_by;

-- Per active staff member. p_from (a Sydney date) limits every count to on/after that day; null = all time.
create function team_stats(p_from date default null)
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
          and (p_from is null or (e.at at time zone 'Australia/Sydney')::date >= p_from))::int as taken,
      (select count(*) from call_logs cl
        where cl.staff_id = s.id
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

-- Refreshers by month of last-done date and segment, out-of-window lines included.
create function cohort_counts(p_type text default null, p_location text default null)
returns table(month date, segment text, n int)
language plpgsql stable security definer set search_path = public as $$
#variable_conflict use_column
begin
  if not is_staff() then raise exception 'not staff' using errcode = '42501'; end if;
  return query
  select date_trunc('month', l.last_done)::date,
         case when l.status = 'won' and l.won_without_call then 'booked_without_call' else l.status end,
         count(*)::int
    from lines l
   where (p_type is null or l.refresher_type = p_type)
     and (p_location is null or l.location = p_location)
   group by 1, 2
   order by 1, 2;
end;
$$;

revoke all on v_cards from public, anon, authenticated, service_role;
grant select on v_cards to authenticated;

revoke execute on function team_stats(date), cohort_counts(text, text) from public, anon, authenticated, service_role;
grant execute on function team_stats(date), cohort_counts(text, text) to authenticated;
