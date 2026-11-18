// Tests for the page's pure functions (the RC object in <script id="rc-logic"> in index.html).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');
const m = html.match(/<script id="rc-logic">([\s\S]*?)<\/script>/);
if (!m) throw new Error('index.html has no <script id="rc-logic"> block');
const sandbox = { module: { exports: {} } };
vm.runInNewContext(m[1], sandbox);
const RC = sandbox.module.exports;
// Objects from the vm context have a different prototype chain; compare plain copies.
const plain = (x) => JSON.parse(JSON.stringify(x));

test('esc neutralises markup and quotes', () => {            // Review Focus 4
  assert.equal(RC.esc(`<img src=x onerror=1> & "O'Brien"`), '&lt;img src=x onerror=1&gt; &amp; &quot;O&#39;Brien&quot;');
  assert.equal(RC.esc(null), '');
  assert.equal(RC.esc(undefined), '');
  assert.equal(RC.esc(42), '42');
});

test('profileUrl', () => assert.equal(RC.profileUrl(14929308),
  'https://kallibr.app.axcelerate.com/management/management2/contact_view.cfm?contactID=14929308'));

test('sydneyToday is the Sydney date, not UTC', () => {       // Review Focus 3
  assert.equal(RC.sydneyToday(new Date('2026-11-19T22:30:00Z')), '2026-11-20');
  assert.equal(RC.sydneyToday(new Date('2026-07-01T13:59:00Z')), '2026-07-01');   // winter: UTC+10
  assert.equal(RC.sydneyToday(new Date('2026-07-01T14:00:00Z')), '2026-07-02');
});

test('fmtMonth and fmtDate', () => {
  assert.equal(RC.fmtMonth('2024-02-10'), 'Feb 2024');
  assert.equal(RC.fmtDate('2026-11-12'), '12 Nov 2026');
  assert.equal(RC.fmtDate(null), '');
});

test('dueLabel', () => {
  assert.deepEqual(plain(RC.dueLabel('2026-02-10', '2026-11-18')), { text: 'Overdue since Feb 2026', overdue: true });
  assert.deepEqual(plain(RC.dueLabel('2027-03-18', '2026-11-18')), { text: 'Due Mar 2027', overdue: false });
  assert.deepEqual(plain(RC.dueLabel('2026-11-18', '2026-11-18')), { text: 'Due Nov 2026', overdue: false });
});

const card = (o) => ({ card_key: 'B:1', target_name: 'Someone', org_name: null, claimed_by: null, do_not_call: false,
  open_lines: 1, overdue_lines: 0, earliest_due: '2026-12-01', locations: [], types: [], callback_on: null, kind: 'booker', ...o });

test('sortQueue: biggest first, then most overdue', () => {
  const cards = [card({ card_key: 'a', open_lines: 3, earliest_due: '2026-05-01' }),
                 card({ card_key: 'b', open_lines: 9, earliest_due: '2026-08-01' }),
                 card({ card_key: 'c', open_lines: 9, earliest_due: '2026-01-01' })];
  assert.deepEqual(plain(RC.sortQueue(cards).map((c) => c.card_key)), ['c', 'b', 'a']);
  assert.deepEqual(cards.map((c) => c.card_key), ['a', 'b', 'c'], 'does not reorder its input');
});

test('filterCards by state, type, due and search', () => {
  const a = card({ card_key: 'a', locations: ['NSW', 'QLD'], types: ['Heights'], overdue_lines: 1, open_lines: 1,
                   target_name: 'Pat Booker', org_name: 'Acme Pty Ltd', kind: 'booker' });
  const b = card({ card_key: 'b', locations: ['VIC'], types: ['HSR'], overdue_lines: 0, open_lines: 2,
                   target_name: 'Kim Tran', org_name: null, kind: 'individual' });
  const keys = (f) => plain(RC.filterCards([a, b], f).map((c) => c.card_key));
  assert.deepEqual(keys({}), ['a', 'b']);
  assert.deepEqual(keys({ state: 'QLD' }), ['a']);
  assert.deepEqual(keys({ state: 'NSW' }), ['a']);
  assert.deepEqual(keys({ state: 'VIC' }), ['b']);
  assert.deepEqual(keys({ type: 'HSR' }), ['b']);
  assert.deepEqual(keys({ due: 'overdue' }), ['a']);
  assert.deepEqual(keys({ due: 'upcoming' }), ['b']);
  assert.deepEqual(keys({ kind: 'individual' }), ['b']);
  assert.deepEqual(keys({ search: 'acme' }), ['a']);
  assert.deepEqual(keys({ search: 'PAT' }), ['a']);
  assert.deepEqual(keys({ search: '  kim ' }), ['b']);
  assert.deepEqual(keys({ state: 'QLD', type: 'HSR' }), []);
  assert.deepEqual(keys({ state: 'NSW', type: 'Heights', due: 'overdue', search: 'pat' }), ['a']);
  assert.deepEqual(keys({ state: '', type: '', due: '', kind: '', search: '' }), ['a', 'b']);
});

test('queueCards hides claimed, do-not-call and finished cards', () => {
  const cards = [card({ card_key: 'open' }), card({ card_key: 'mine', claimed_by: 'u1' }),
                 card({ card_key: 'dnc', do_not_call: true }), card({ card_key: 'done', open_lines: 0 })];
  assert.deepEqual(plain(RC.queueCards(cards).map((c) => c.card_key)), ['open']);
});

test('myCards puts due call-backs first', () => {
  const cards = [card({ card_key: 'none', claimed_by: 'me', open_lines: 5, earliest_due: '2026-01-01' }),
                 card({ card_key: 'later', claimed_by: 'me', callback_on: '2026-11-25', open_lines: 2 }),
                 card({ card_key: 'due', claimed_by: 'me', callback_on: '2026-11-17', open_lines: 1 }),
                 card({ card_key: 'today', claimed_by: 'me', callback_on: '2026-11-18', open_lines: 1 }),
                 card({ card_key: 'other', claimed_by: 'them', callback_on: '2026-11-01' }),
                 card({ card_key: 'finished', claimed_by: 'me', open_lines: 0 })];
  assert.deepEqual(plain(RC.myCards(cards, 'me', '2026-11-18').map((c) => c.card_key)), ['due', 'today', 'none', 'later']);
});

test('staleBanner only after 36 hours', () => {
  const now = Date.parse('2026-11-18T09:00:00+11:00');
  assert.equal(RC.staleBanner(new Date(now - 35 * 3600e3).toISOString(), now), null);
  const msg = RC.staleBanner(new Date(now - 37 * 3600e3).toISOString(), now);
  assert.match(msg, /out of date/);
  assert.match(msg, /16 Nov 2026/);
  assert.match(RC.staleBanner(null, now), /not been updated/);
});

// ---------- Task 10: card view ----------
const T = '2026-11-18';
const L = (id, contact_id, refresher_type, due_date, status = 'not_called', extra = {}) =>
  ({ id, contact_id, refresher_type, due_date, status, in_window: true, last_done: '2024-01-01', ...extra });
const LINES = [L(13, 2, 'Heights', '2027-01-10'), L(12, 1, 'Heights', '2026-03-07'), L(11, 1, 'Confined Space', '2026-02-05', 'pending'),
               L(14, 3, 'Heights', '2025-12-01', 'won')];
const STUDENTS = [{ contact_id: 1, full_name: 'Sam Lee' }, { contact_id: 2, full_name: 'Kim Tran' },
                  { contact_id: 3, full_name: 'Ali Khan' }, { contact_id: 4, full_name: 'No Lines' }];

test('groupLines sorts and flags due-for-both', () => {
  // student 1: Confined Space due 2026-02-05 (open) + Heights due 2026-03-07 (open); student 2: Heights due 2027-01-10 (open); student 3: Heights won
  const g = RC.groupLines(LINES, STUDENTS, T);
  assert.deepEqual(plain(g.map((x) => [x.contact_id, x.dueForBoth, x.rows.length])), [[1, true, 2], [2, false, 1], [3, false, 1]]);
  assert.deepEqual(plain(g[0].rows.map((r) => r.id)), [11, 12]);
  assert.equal(g[0].full_name, 'Sam Lee');
});

test('a second line that is already lost does not count as due-for-both', () => {
  const g = RC.groupLines([L(1, 1, 'Heights', '2026-03-07'), L(2, 1, 'Confined Space', '2026-02-05', 'lost')], STUDENTS, T);
  assert.equal(g[0].dueForBoth, false);
});

test('an out-of-window line is not open', () => {
  const g = RC.groupLines([L(1, 1, 'Heights', '2026-03-07'), L(2, 1, 'HSR', '2024-01-01', 'not_called', { in_window: false })], STUDENTS, T);
  assert.equal(g[0].dueForBoth, false);
  assert.equal(RC.isOpen(L(2, 1, 'HSR', '2024-01-01', 'not_called', { in_window: false })), false);
});

test('cardSummary', () => {
  assert.equal(RC.cardSummary(RC.groupLines(LINES, STUDENTS, T), T), '2 students · 3 refreshers · 2 overdue, 1 due by Jan 2027');
  assert.equal(RC.cardSummary(RC.groupLines([L(1, 1, 'Heights', '2027-03-07')], STUDENTS, T), T), '1 student · 1 refresher · 1 due by Mar 2027');
  assert.equal(RC.cardSummary(RC.groupLines([L(1, 1, 'Heights', '2026-03-07'), L(2, 1, 'HSR', '2026-04-01')], STUDENTS, T), T),
    '1 student · 2 refreshers · 2 overdue');
  assert.equal(RC.cardSummary(RC.groupLines([L(1, 1, 'Heights', '2026-03-07', 'won')], STUDENTS, T), T), 'No open refreshers');
});

test('buildOutcomes drops blanks', () => {
  assert.deepEqual(plain(RC.buildOutcomes({ 11: 'will_book', 12: '' })), [{ line_id: 11, outcome: 'will_book' }]);
  assert.deepEqual(plain(RC.buildOutcomes({ 3: null, 4: 'no_answer', 5: undefined })), [{ line_id: 4, outcome: 'no_answer' }]);
});

test('validateCallLog', () => {
  assert.equal(RC.validateCallLog([], null, T), 'Choose an outcome for at least one refresher.');
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'call_back' }], null, T), 'Pick a call-back date.');
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'call_back' }], '2026-11-17', T), "The call-back date can't be in the past.");
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'will_book' }], null, T), null);
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'call_back' }], T, T), null);
  assert.equal(RC.validateCallLog([{ line_id: 1, outcome: 'info_sent' }], '2026-11-01', T), "The call-back date can't be in the past.");
});

test('every outcome maps to pending or lost, never won', () => {
  assert.ok(RC.OUTCOMES.every((o) => ['pending', 'lost'].includes(o.status)));
  assert.deepEqual(plain(RC.OUTCOMES.map((o) => o.code)),
    ['no_answer', 'call_back', 'info_sent', 'will_book', 'not_needed', 'went_elsewhere', 'left_company', 'do_not_call']);
  assert.equal(RC.outcomeLabel('left_company'), 'Left the company');
  assert.deepEqual(plain(RC.STATUS_BADGE.won), ['badge-success', '🟢 Won']);
});

test('fmtDateTime is Sydney time', () => {
  assert.equal(RC.fmtDateTime('2026-11-19T22:30:00Z'), '20 Nov 2026, 9:30 am');
  assert.equal(RC.fmtDateTime('2026-06-30T04:05:00Z'), '30 Jun 2026, 2:05 pm');
  assert.equal(RC.fmtDateTime('2026-11-18T13:00:00Z'), '19 Nov 2026, 12:00 am');
});
