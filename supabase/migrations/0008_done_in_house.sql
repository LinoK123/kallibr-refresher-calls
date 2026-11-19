-- New call outcome "Done in-house": the student's company ran the refresher itself (owner's request, 20 Nov 2026).
-- Replaces outcome_status from 0002 with one more lost outcome.

create or replace function outcome_status(p_outcome text) returns text
language plpgsql immutable as $$
declare s text;
begin
  s := case p_outcome
    when 'no_answer' then 'pending' when 'call_back' then 'pending'
    when 'info_sent' then 'pending' when 'will_book' then 'pending'
    when 'not_needed' then 'lost' when 'went_elsewhere' then 'lost'
    when 'done_in_house' then 'lost'
    when 'left_company' then 'lost' when 'do_not_call' then 'lost'
  end;
  if s is null then
    raise exception 'unknown outcome: %', p_outcome using errcode = '22023';
  end if;
  return s;
end;
$$;

revoke execute on function outcome_status(text) from public, anon, authenticated, service_role;
grant execute on function outcome_status(text) to authenticated, service_role;
