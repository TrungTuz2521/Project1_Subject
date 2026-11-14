"""Scoring candidate pairs, the scan, and turning a pair into a game."""
from sqlalchemy import select
from app.contracts.enums import SKILLS
from app.models import Booking, Match, MatchParticipant, MatchPost, Payment, Pitch, Team, User
from app.services import booking_policy as policy, booking_service, notification_service
from app.services.match_requests.rules import (
    BOOKED_PAIR_LAST_CALL, BOOKED_PAIR_WAIT, CUTOFF, JOIN, MATCH_HOLD_SECONDS, OPPONENT, RECRUIT, RULE_NAMES,
    SKILL_NAMES, TYPES, agreed_rule, booking_parties, busy, contact_line, label, no_shows, party_users,
    slots, team_line)

def skill_gap(a, b):
    return abs(SKILLS.index(a.skill_level) - SKILLS.index(b.skill_level))

def _skill_points(gap):
    return 40 if gap == 0 else 20 if gap == 1 else 0

def opponent_fit(ctx, a, b, now):
    """None, or (tier, points, common slots). Tier 0 = one side already booked (preferred), 1 = neither,
    2 = both booked (one booking is merged into the other)."""
    if a.creator_id == b.creator_id or a.team_id == b.team_id:
        return None
    if a.pitch_type != b.pitch_type or (a.payment_rule and b.payment_rule and a.payment_rule != b.payment_rule):
        return None
    gap = skill_gap(a, b)
    if gap > min(a.skill_tolerance if a.skill_tolerance is not None else 1, b.skill_tolerance if b.skill_tolerance is not None else 1):
        return None
    if party_users(a) & party_users(b):
        return None
    theirs = {s for s, _ in slots(b, now)}
    common = [(s, e) for s, e in slots(a, now) if s in theirs]
    if not common:
        return None
    booked = sum(1 for p in (a, b) if p.booking_id)
    if booked == 2 and now - max(a.created_at, b.created_at) < BOOKED_PAIR_WAIT and min(a.expiry_time, b.expiry_time) - now > BOOKED_PAIR_LAST_CALL:
        return None
    tier = {1: 0, 0: 1, 2: 2}[booked]
    points = 60 + _skill_points(gap) - 10 * min(3, no_shows(ctx, a.creator_id) + no_shows(ctx, b.creator_id))
    return tier, points, common

def join_fit(ctx, recruit, joiner, now, room=None):
    if recruit.creator_id == joiner.creator_id or not recruit.match_time:
        return None
    room = recruit.required_players if room is None else room
    if joiner.current_players > (room or 0):
        return None
    if joiner.pitch_type and joiner.pitch_type != recruit.pitch_type:
        return None
    gap = skill_gap(recruit, joiner)
    if gap > min(recruit.skill_tolerance if recruit.skill_tolerance is not None else 1, joiner.skill_tolerance if joiner.skill_tolerance is not None else 1):
        return None
    if recruit.match_time - now < CUTOFF or recruit.match_time not in {s for s, _ in slots(joiner, now)}:
        return None
    booking = ctx.session.get(Booking, recruit.booking_id) if recruit.booking_id else None
    if booking is None or booking.status != 'CONFIRMED' or joiner.creator_id in booking_parties(booking) | party_users(recruit):
        return None
    return 60 + _skill_points(gap) + (10 if joiner.current_players == room else 0)


def scan(only_post_id=None):
    """One pass: plan every candidate pair without locks, best first, then pair each in its own transaction."""
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        now = ctx.now()
        rows = list(ctx.session.scalars(select(MatchPost).where(MatchPost.status == 'OPEN', MatchPost.expiry_time > now,
                                                                MatchPost.post_type.in_(TYPES)).order_by(MatchPost.created_at, MatchPost.post_id)))
        teams = [p for p in rows if p.post_type == OPPONENT]
        opponent_pairs = []
        for i, a in enumerate(teams):
            for b in teams[i + 1:]:
                if only_post_id not in (None, a.post_id, b.post_id):
                    continue
                fit = opponent_fit(ctx, a, b, now)
                if fit:
                    tier, points, _ = fit
                    first, second = sorted((a, b), key=lambda p: (p.created_at, p.post_id))
                    # Best fit first; among equal fits prefer using a pitch already booked, then whoever asked first.
                    opponent_pairs.append(((-points, tier, first.created_at, second.created_at, first.post_id, second.post_id), first.post_id, second.post_id))
        recruits = [p for p in rows if p.post_type == RECRUIT]
        joiners = [p for p in rows if p.post_type == JOIN]
        join_pairs = []
        for r in recruits:
            for j in joiners:
                if only_post_id not in (None, r.post_id, j.post_id):
                    continue
                points = join_fit(ctx, r, j, now)
                if points:
                    join_pairs.append(((-points, j.created_at, r.created_at, j.post_id, r.post_id), r.post_id, j.post_id))
    used, made = set(), []
    for _, first, second in sorted(opponent_pairs):
        if first in used or second in used:
            continue
        match_id = pair_opponents(first, second)
        if match_id:
            used.update((first, second))
            made.append(match_id)
    joined = []
    for _, recruit_id, joiner_id in sorted(join_pairs):
        if joiner_id in used:
            continue
        if pair_join(recruit_id, joiner_id):
            used.add(joiner_id)
            joined.append(joiner_id)
    return {'scanned_count': len(rows), 'matches': made, 'joined_requests': joined}

def _free_pitch(ctx, pitch_type, common):
    for start, end in common:
        pitch_id = booking_service.find_match_pitch(ctx, pitch_type=pitch_type, start_time=start, end_time=end)
        if pitch_id:
            return pitch_id, start, end
    return None

def pair_opponents(first_id, second_id):
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        a, b = ctx.session.get(MatchPost, first_id), ctx.session.get(MatchPost, second_id)
        if a is None or b is None:
            return None
        now = ctx.now()
        fit = opponent_fit(ctx, a, b, now)
        if not fit:
            return None
        bookings = [ctx.session.get(Booking, p.booking_id) for p in (a, b) if p.booking_id]
        choice = None if bookings else _free_pitch(ctx, a.pitch_type, fit[2])
        if not bookings and choice is None:
            return None
        # Lock order: users, teams, pitches, posts, matches, bookings, payments.
        ctx.locks.users(party_users(a) | party_users(b))
        ctx.locks.lock(Team, [a.team_id, b.team_id])
        ctx.locks.lock(Pitch, [bk.pitch_id for bk in bookings] + ([choice[0]] if choice else []))
        ctx.locks.lock(MatchPost, [a.post_id, b.post_id])
        bookings = ctx.locks.lock(Booking, [bk.booking_id for bk in bookings])
        ctx.locks.lock(Payment, [p.payment_id for bk in bookings for p in booking_service.payments_of(ctx, bk.booking_id)])
        if a.status != 'OPEN' or b.status != 'OPEN' or any(bk.status != 'CONFIRMED' for bk in bookings):
            return None
        fit = opponent_fit(ctx, a, b, now)
        if not fit:
            return None
        tier, points, common = fit
        if len(bookings) == 0:
            start, end = choice[1], choice[2]
        else:
            start, end = bookings[0].start_time, bookings[0].end_time
            if (start, end) not in common or any((bk.start_time, bk.end_time) != (start, end) for bk in bookings):
                return None
        if busy(ctx, party_users(a) | party_users(b), start, end, ignore_post_ids=(a.post_id, b.post_id)):
            return None
        if len(bookings) == 0:
            return _pair_new_booking(ctx, a, b, choice[0], start, end, points)
        if len(bookings) == 2:
            keep, drop = sorted(bookings, key=lambda bk: (bk.created_at, bk.booking_id))
            _merge_bookings(ctx, keep, drop)
            booking = keep
        else:
            booking = bookings[0]
        return _pair_on_booking(ctx, a, b, booking, points)

def _owner_post(a, b, booking):
    return (a, b) if a.booking_id == booking.booking_id else (b, a)

def _pair_on_booking(ctx, a, b, booking, points):
    owner, other = _owner_post(a, b, booking)
    now = ctx.now()
    match = Match(post_id=owner.post_id, opponent_post_id=other.post_id, booking_id=booking.booking_id, match_time=booking.start_time,
                  compatibility_score=float(points), status='CONFIRMED', confirmed_at=now)
    ctx.session.add(match)
    ctx.session.flush()
    for post in (owner, other):
        post.status = 'MATCHED'
        post.match_time, post.end_time, post.pitch_id = booking.start_time, booking.end_time, booking.pitch_id
    pitch = ctx.session.get(Pitch, booking.pitch_id)
    for me, them in ((owner, other), (other, owner)):
        merged = me.booking_id and me.booking_id != booking.booking_id
        extra = (' Lượt sân bạn đặt cùng giờ đã được gộp, tiền cọc của bạn được tính vào tiền sân này, phần còn lại trả tại quầy.'
                 if merged else ' Không cần đặt cọc thêm.')
        notification_service.notify(ctx, [me.creator_id], 'MATCH_CONFIRMED', 'Đã tìm được đối',
            f'{team_line(ctx, them)} sẽ đá với đội bạn lúc {label(booking.start_time)} tại {pitch.pitch_name}.{extra} '
            f'Cách chia tiền: {RULE_NAMES[agreed_rule(a, b)]}. Liên hệ đội trưởng: {contact_line(ctx, them.creator_id)}.', match_id=match.match_id)
    ctx.session.flush()
    return match.match_id

def _merge_bookings(ctx, keep, drop):
    """Both teams booked the same time: play on the earlier booking. The other booking closes and its
    deposits move onto the kept one, so they count towards the pitch fee instead of being refunded."""
    for payment in booking_service.payments_of(ctx, drop.booking_id):
        if payment.payment_type == 'BOOKING_DEPOSIT' and payment.status == 'SUCCESS':
            payment.booking_id = keep.booking_id
            payment.note = policy.add_note(payment.note, f'MERGED_FROM #{drop.booking_id} (ghep keo)')
        elif payment.status == 'PENDING':
            payment.status = 'FAILED'
            payment.note = policy.add_note(payment.note, 'Booking gop vao keo')
    drop.status = 'CANCELLED'
    drop.note = policy.add_note(drop.note, f'Gop vao booking #{keep.booking_id} khi ghep keo; coc chuyen sang booking do')
    keep.note = policy.add_note(keep.note, f'Ghep keo: nhan coc tu booking #{drop.booking_id}')
    ctx.session.flush()

def _pair_new_booking(ctx, a, b, pitch_id, start, end, points):
    """Neither team booked: the system holds a pitch and each team pays half the deposit within twelve hours."""
    from app.contracts.errors import SlotUnavailable
    match = Match(post_id=a.post_id, opponent_post_id=b.post_id, match_time=start, compatibility_score=float(points), status='SUGGESTED')
    ctx.session.add(match)
    ctx.session.flush()
    try:
        hold = booking_service.create_match_hold(ctx, match_id=match.match_id, pitch_id=pitch_id, start_time=start, end_time=end,
                                                 source_user_id=a.creator_id, opponent_user_id=b.creator_id, payment_rule=agreed_rule(a, b),
                                                 hold_seconds=MATCH_HOLD_SECONDS)
    except SlotUnavailable:
        ctx.session.rollback()
        return None
    match.booking_id = hold.booking_id
    for post in (a, b):
        post.status = 'MATCHED'
        post.match_time, post.end_time, post.pitch_id = start, end, pitch_id
    pitch = ctx.session.get(Pitch, pitch_id)
    shares = {item['user_id']: item['amount'] for item in hold.payer_plan}
    for me, them in ((a, b), (b, a)):
        notification_service.notify(ctx, [me.creator_id], 'BOOKING_HOLD', 'Đã tìm được đối, cần đặt cọc',
            f'{team_line(ctx, them)} sẽ đá với đội bạn lúc {label(start)} tại {pitch.pitch_name}. Hệ thống đã giữ sân. '
            f'Phần cọc của đội bạn là {policy.vnd(shares[me.creator_id])}, cần trả trước {label(hold.hold_expires_at)} '
            f'trong Lịch đã đặt. Cách chia tiền: {RULE_NAMES[agreed_rule(a, b)]}. Quá hạn mà một đội chưa cọc thì kèo bị hủy.', match_id=match.match_id)
    ctx.session.flush()
    return match.match_id

def pair_join(recruit_id, joiner_id):
    from app.infrastructure.unit_of_work import UnitOfWork
    with UnitOfWork() as ctx:
        recruit, joiner = ctx.session.get(MatchPost, recruit_id), ctx.session.get(MatchPost, joiner_id)
        if recruit is None or joiner is None:
            return False
        ctx.locks.users(party_users(recruit) | party_users(joiner))
        ctx.locks.lock(Team, [recruit.team_id])
        ctx.locks.lock(MatchPost, [recruit_id, joiner_id])
        if recruit.status != 'OPEN' or joiner.status != 'OPEN':
            return False
        now = ctx.now()
        if not join_fit(ctx, recruit, joiner, now):
            return False
        if busy(ctx, party_users(joiner), recruit.match_time, recruit.end_time, ignore_post_ids=(joiner.post_id,)):
            return False
        participant = ctx.session.scalar(select(MatchParticipant).where(MatchParticipant.post_id == recruit_id,
                                                                        MatchParticipant.user_id == joiner.creator_id))
        if participant is None:
            participant = MatchParticipant(post_id=recruit_id, user_id=joiner.creator_id)
            ctx.session.add(participant)
        participant.status, participant.joined_at = 'ACCEPTED', now
        recruit.required_players -= joiner.current_players
        if recruit.required_players <= 0:
            recruit.required_players, recruit.status = 0, 'MATCHED'
        joiner.status, joiner.matched_post_id = 'MATCHED', recruit_id
        joiner.match_time, joiner.end_time, joiner.pitch_id = recruit.match_time, recruit.end_time, recruit.pitch_id
        pitch = ctx.session.get(Pitch, recruit.pitch_id)
        fee = f' Chi phí mỗi người: {policy.vnd(recruit.required_deposit)}, trả cho đội trưởng.' if recruit.required_deposit else ''
        who = ctx.session.get(User, joiner.creator_id)
        notification_service.notify(ctx, [joiner.creator_id], 'TEAM_JOINED', 'Đã tìm được trận để đá ké',
            f'Bạn{" và " + str(joiner.current_players - 1) + " bạn đi cùng" if joiner.current_players > 1 else ""} được ghép vào '
            f'trận lúc {label(recruit.match_time)} tại {pitch.pitch_name}.{fee} Liên hệ đội trưởng: {contact_line(ctx, recruit.creator_id)}.')
        left = f'Còn thiếu {recruit.required_players} người.' if recruit.required_players else 'Đã đủ người.'
        notification_service.notify(ctx, [recruit.creator_id], 'TEAM_JOINED', 'Có người đá cùng',
            f'{who.full_name} ({SKILL_NAMES[joiner.skill_level]}, {joiner.current_players} người) sẽ đá cùng đội bạn lúc '
            f'{label(recruit.match_time)}. Số điện thoại: {who.phone or "chưa cập nhật"}. {left}')
        ctx.session.flush()
        return True
