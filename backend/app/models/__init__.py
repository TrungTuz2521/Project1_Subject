"""Models owned by Đức; Tú registers his models on the same db.metadata."""
from sqlalchemy import UniqueConstraint
from app.extensions import db
from app.utils.time import UTCDateTime, utcnow

class Timestamped:
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

class User(Timestamped, db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(255))
    google_id = db.Column(db.String(100), unique=True)
    role = db.Column(db.String(16), nullable=False, default='PLAYER')
    skill_level = db.Column(db.String(16), nullable=False, default='AMATEUR')
    fair_play_score = db.Column(db.Float, nullable=False, default=100)
    match_priority = db.Column(db.Integer, nullable=False, default=100)
    radar_stats = db.Column(db.JSON)
    status = db.Column(db.String(16), nullable=False, default='ACTIVE')

class Team(Timestamped, db.Model):
    __tablename__ = 'teams'
    team_id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    creation_type = db.Column(db.String(16), nullable=False, default='USER_CREATED')
    status = db.Column(db.String(16), nullable=False, default='ACTIVE')

class TeamMember(db.Model):
    __tablename__ = 'team_members'
    __table_args__ = (UniqueConstraint('team_id', 'user_id'),)
    team_member_id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.team_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='MEMBER')
    status = db.Column(db.String(16), nullable=False, default='ACTIVE')
    joined_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

class MatchPost(Timestamped, db.Model):
    __tablename__ = 'match_posts'
    post_id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.team_id'))
    pitch_id = db.Column(db.Integer)
    booking_id = db.Column(db.Integer)
    post_type = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    pitch_type = db.Column(db.String(16))
    match_time = db.Column(UTCDateTime())
    end_time = db.Column(UTCDateTime())
    skill_level = db.Column(db.String(16), nullable=False)
    payment_rule = db.Column(db.String(100))
    required_players = db.Column(db.Integer)
    current_players = db.Column(db.Integer, nullable=False, default=1)
    required_deposit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expiry_time = db.Column(UTCDateTime(), nullable=False)
    is_fallback_scanned = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32), nullable=False, default='OPEN')

class MatchParticipant(db.Model):
    __tablename__ = 'match_participants'
    __table_args__ = (UniqueConstraint('post_id', 'user_id'),)
    participant_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    status = db.Column(db.String(16), nullable=False, default='PENDING')
    joined_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

class MatchProposal(Timestamped, db.Model):
    __tablename__ = 'match_proposals'
    proposal_id = db.Column(db.Integer, primary_key=True)
    source_post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'), nullable=False)
    target_post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'))
    candidate_user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    proposal_type = db.Column(db.String(16), nullable=False)
    compatibility_score = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default='PENDING_CONFIRMATION')
    expires_at = db.Column(UTCDateTime(), nullable=False)
    confirmed_at = db.Column(UTCDateTime())

class ProposalConfirmation(db.Model):
    __tablename__ = 'proposal_confirmations'
    __table_args__ = (UniqueConstraint('proposal_id', 'user_id'),)
    confirmation_id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('match_proposals.proposal_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    decision = db.Column(db.String(16), nullable=False, default='PENDING')
    responded_at = db.Column(UTCDateTime())
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)

class Match(Timestamped, db.Model):
    __tablename__ = 'matches'
    match_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'), nullable=False)
    opponent_post_id = db.Column(db.Integer, db.ForeignKey('match_posts.post_id'))
    booking_id = db.Column(db.Integer)
    proposal_id = db.Column(db.Integer, db.ForeignKey('match_proposals.proposal_id'), unique=True)
    match_time = db.Column(UTCDateTime(), nullable=False)
    compatibility_score = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(16), nullable=False, default='SUGGESTED')
    confirmed_at = db.Column(UTCDateTime())

class Notification(db.Model):
    __tablename__ = 'notifications'
    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    proposal_id = db.Column(db.Integer, db.ForeignKey('match_proposals.proposal_id'))
    match_id = db.Column(db.Integer, db.ForeignKey('matches.match_id'))
    notification_type = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    delivery_channel = db.Column(db.String(16), nullable=False, default='IN_APP')
    delivery_status = db.Column(db.String(16), nullable=False, default='SENT')
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(UTCDateTime(), nullable=False, default=utcnow)
    sent_at = db.Column(UTCDateTime(), default=utcnow)
    read_at = db.Column(UTCDateTime())
