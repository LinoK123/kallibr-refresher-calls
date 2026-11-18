# Current booking contact: design (short)

Date: 18 November 2026
Status: approved by the owner 18 November 2026 ("yes good plan")
Changes: spec `2026-11-18-refresher-call-tool-design.md` section 5.3 (card placement)

## Intent

Refreshers fall due about two years after a course, and by then the person who booked it has often stopped booking for that company. Example: Kim Spicer was the booking contact on NBN Co's card, but her last booking for NBN Co was in May 2025. NBN Co's bookings are now made by Kavita Dsilva for NSW and Therese Stapleton for QLD. Staff should ring the company's current booker for the student's state, and a company whose states are booked by different people should become separate cards.

## The rule

A student's first-pass card comes from spec 5.3 as today. Then, for a student whose organisation is a real company (not blank, not "Cash - Individual"):

1. **Booker card, booker still active:** if that booker has made a real booking for the company in the last 12 months, the student stays on that booker's card. A booking is in the window when its booked date (or, if missing, its class start date) is on or after today minus 12 months.
2. **Booker card with a quiet booker, or an organisation card:** the student goes to the company's **current booker for the student's state**. That's the requester with the most real bookings for that company at classes in that state in the last 12 months, any course. Ties go to the latest booking, then to the lowest contact ID.
   - If nobody booked for the company in that state, use the company's busiest booker in any state, chosen the same way.
   - If nobody booked for the company at all in the last 12 months, the first-pass card stands.
3. **Individual cards** (self-bookers, blank or cash organisations) are unchanged.

"Requester", "real booking" and "Kallibr staff are not bookers" keep their spec 5.3 meanings: staff names and the ignore list never become a current booker, and neither does a student who booked themselves. After this step, the existing "one person, one card" merge and sticky placement apply as before: a student with a logged call never moves.

## Approaches

1. **Replace only quiet bookers; current booker per company and state** (chosen). It matches the request and leaves companies with several active bookers alone. Real data on 18 Nov 2026: 1,258 students move (944 from quiet bookers, 314 from organisation cards), and cards go from 1,279 to 1,151. NBN Co becomes Therese (54, QLD) and Kavita (10, NSW), plus 6 self-bookers.
2. Always use the company's busiest booker: moves 1,500–1,700 students and merges companies that have several active bookers. Rejected.
3. Also move self-bookers to the company booker: not wanted; self-bookers keep their own card.

## Effect the owner accepted

A held card whose booker has gone quiet loses its students who haven't been called yet, to the company's current booker. Students with a logged call stay.
