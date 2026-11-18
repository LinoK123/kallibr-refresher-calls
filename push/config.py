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
IGNORE_BOOKER_CONTACT_IDS = ()         # extra contact IDs never treated as bookers

MAX_SOURCE_AGE_HOURS = 36
MAX_LINE_DROP = 0.20
CHUNK = 500
