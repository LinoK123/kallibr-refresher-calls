-- Cards taken skips a card released with no call logged (owner's request, 19 Nov 2026).
-- Replaces team_stats from 0005 with one change: a take counts only if the card is still theirs or they
-- logged a call on it after taking it.

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
          -- still theirs, or they logged a call on it after taking it: a take released with no call is a mis-click
          and (exists (select 1 from cards c where c.card_key = e.card_key and c.claimed_by = s.id)
               or exists (select 1 from call_logs cl
                           where cl.card_key = e.card_key and cl.staff_id = s.id and cl.called_at >= e.at)))::int as taken,
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

revoke execute on function team_stats(date) from public, anon, authenticated, service_role;
grant execute on function team_stats(date) to authenticated;
