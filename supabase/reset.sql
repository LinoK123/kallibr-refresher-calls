-- TEST USE ONLY: drops everything the migrations create, so they can be applied again from scratch.
-- Never run this against the live project.

drop table if exists
  stage_history, stage_checks, stage_lines, stage_students,
  sync_runs, card_events, line_outcomes, call_logs, course_history, lines, students, cards, staff
  cascade;

drop function if exists outcome_status(text) cascade;
drop function if exists sydney_today() cascade;
drop function if exists current_staff_id() cascade;
drop function if exists is_staff() cascade;
drop function if exists is_manager() cascade;
