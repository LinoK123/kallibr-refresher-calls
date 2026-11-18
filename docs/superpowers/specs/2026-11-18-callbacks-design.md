# Call-backs list and Monday email: design (short)

Date: 18 November 2026
Status: approved by the owner 18 November 2026 ("yes, build both")

## Intent

Staff need to see the call-backs they've promised: the overdue ones, today's, and those coming up. Every Monday each person should get an email listing their overdue call-backs and the week's call-backs.

## Decided

**Which call-backs count.** A call-back is a held card with a call-back date and at least one open refresher. It only counts if it was set while the current holder held the card: a date set before their claim date (Sydney time) is a leftover from a previous holder and is ignored. This is the same rule as the existing "🟡 Call back today" badge.

**Buckets.**
- **Overdue:** before today.
- **Today.**
- **This week:** after today, up to Sunday (weeks run Monday to Sunday, Sydney time).
- **Later:** after Sunday.

**Site.**
- **My cards** gets a **📅 Your call-backs** section above the table. It lists the viewer's call-backs soonest first, each with a bucket badge, the card name and organisation, the date (for example "was due Mon 16 Nov", or "Fri 20 Nov") and **Open →**.
- The **People** page gets the same list for the picked person; for All team members it adds who holds each card.
- If there are none, the section says how to add one.

**Monday email.**
- **When:** the nightly push on the designated PC sends it after a successful push. It goes out on the first successful run of each Monday-to-Sunday week, so normally Monday morning, or the first run after that if the PC was off. It is never sent twice in a week; a marker file in the KallibrAgent folder records the week last sent.
- **Who and what:** each active team member with at least one overdue or this-week call-back gets one email listing those, with the card name, organisation and date, and a link to the site. People with none get nothing.
- **How it's sent:** it uses the same Gmail sender as the sign-in codes (already allowed in Microsoft 365), sending through `smtp.gmail.com:587` with an app password. The Gmail address and app password are stored in Windows Credential Manager (service `kallibr-refresher`) by `py push/refresher_push.py --set-email`; they are never in the repository.
- **Failures:** an email failure never fails the nightly push. The push's log line reports how many were sent, skipped and failed.
- **Testing by hand:** `--send-digest` sends now regardless of the marker, and `--to <address>` limits it to one recipient.

## Approaches

1. **Send from the nightly push on the designated PC** (chosen). It reuses the PC job and the Gmail sender already allowed in Microsoft 365. The only new set-up is one stored password.
2. A scheduled Supabase function: no dependence on the PC, but more set-up, and the Gmail password would also have to live in Supabase. Not chosen.
