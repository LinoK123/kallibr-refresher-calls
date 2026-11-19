-- TEST USE ONLY: drops everything the migrations create, so they can be applied again from scratch.
-- Never run this against the live project.

drop view if exists v_cards cascade;
drop function if exists team_stats(date) cascade;
drop function if exists cohort_counts(text, text) cascade;

drop table if exists
  stage_history, stage_checks, stage_lines, stage_students,
  sync_runs, card_events, line_outcomes, call_logs, course_history, lines, students, cards, staff
  cascade;

drop function if exists apply_push(bigint) cascade;
drop function if exists claim_card(text) cascade;
drop function if exists release_card(text) cascade;
drop function if exists assign_card(text, uuid) cascade;
drop function if exists save_call_log(text, text, date, jsonb, boolean) cascade;
drop function if exists save_call_log(text, text, date, jsonb, boolean, boolean) cascade;
drop function if exists clear_do_not_call(text) cascade;
drop function if exists upsert_staff(text, text, text, boolean) cascade;
drop function if exists outcome_status(text) cascade;
drop function if exists sydney_today() cascade;
drop function if exists current_staff_id() cascade;
drop function if exists is_staff() cascade;
drop function if exists is_manager() cascade;
