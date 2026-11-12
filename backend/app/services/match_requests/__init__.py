"""Matchmaking by request.

Nobody browses other people's posts. A captain or a player states when and how they can play, the
system records it, scans every open request and pairs the best fits, then tells both sides by email
and in the app. Requests are rows of match_posts:

    FIND_OPPONENT    a full team looks for another team, with or without a pitch already booked
    RECRUIT_MEMBERS  a team with a booked game needs N more players
    LOOK_FOR_TEAM    a player (alone or with up to two friends) wants to join a game ("đá ké")

Status reuses the existing ENUM: OPEN = searching, MATCHED = paired, EXPIRED = nothing found before
the cut-off, CANCELLED = withdrawn. Searching stops one day before kick-off.
"""
from app.services.match_requests.rules import (  # noqa: F401
    ACTIVE_MATCH, CUTOFF, JOIN, MATCH_HOLD_SECONDS, OPPONENT, RECRUIT, TYPES, label)
from app.services.match_requests.requests import create_request, edit_request  # noqa: F401
from app.services.match_requests.pairing import scan  # noqa: F401
from app.services.match_requests.lifecycle import booking_closed, cancel_request, close_expired, release_match  # noqa: F401
from app.services.match_requests.views import options, request_data  # noqa: F401
