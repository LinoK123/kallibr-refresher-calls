"""Settings for the refresher push.

Course membership of Confined Space and Heights comes from the course master
(course_refresher_groups). HSR course IDs live here because the master has no HSR group yet.
"""

INTERVAL_MONTHS = {"Confined Space": 24, "Heights": 24, "HSR": 12}
HSR_COURSE_TYPE_IDS = (100882, 101060, 114315)

LOOKBACK_YEARS = 3          # last done within this many years to be on the list
LOOKAHEAD_MONTHS = 4        # due on or before today + this many months

FUTURE_BOOKING_STATUSES = ("Approved", "Booked", "Moved", "Replaced", "Tentative", "Waitlisted")
TENTATIVE_STATUSES = ("Tentative", "Waitlisted")

INDIVIDUAL_ORG_PREFIX = "Cash - Individual"
STAFF_ENTERED_MIN = 50                 # a requester who entered this many bookings is Kallibr staff
CURRENT_BOOKER_MONTHS = 12             # a booker counts as current if they booked for the company within this
IGNORE_BOOKER_CONTACT_IDS = ()         # extra contact IDs never treated as bookers

# Monday call-back email (sent by the nightly push on the designated PC)
SITE_URL = "https://linok123.github.io/kallibr-refresher-calls/"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM_NAME = "Kallibr Refresher Calls"
DIGEST_MARKER = "refresher_digest_week.txt"     # in the KallibrAgent folder: the Monday of the week last sent
REPORT_MARKER = "refresher_report_week.txt"     # in the KallibrAgent folder: the Monday of the week last reported

MAX_SOURCE_AGE_HOURS = 36
MAX_LINE_DROP = 0.20
# A night that would take back more wins than this is treated as bad data and stopped:
# more than max(MAX_REVERSALS_MIN, MAX_REVERSAL_SHARE x current wins). Override with --allow-reversals.
MAX_REVERSALS_MIN = 10
MAX_REVERSAL_SHARE = 0.05
CHUNK = 500
