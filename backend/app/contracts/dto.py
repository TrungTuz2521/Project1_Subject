from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

@dataclass(frozen=True)
class Actor:
    user_id: int
    role: str

@dataclass
class CommandResult:
    outcome: str = 'OK'
    data: Any = None
    error: Any = None
    http_status: int = 200

@dataclass(frozen=True)
class BookingHold:
    booking_id: int
    status: str
    hold_expires_at: datetime
    total_amount: Decimal
    deposit_amount: Decimal
    payer_plan: list[dict]

@dataclass(frozen=True)
class MembershipResult:
    team_id: int
    user_id: int
    participant_id: int
    remaining_players: int
    post_status: str

@dataclass(frozen=True)
class MatchParties:
    match_id: int
    booking_id: int | None
    source: dict
    opponent: dict

@dataclass(frozen=True)
class BookingBalance:
    """Tú computes booking-wide totals; payment_rule is for display only after play."""
    booking_id: int
    payment_rule: str
    total_amount: Decimal
    deposit_collected_amount: Decimal
    remaining_collected_amount: Decimal
    collected_amount: Decimal
    outstanding_amount: Decimal
    payment_status: str
    qr_payload: str | None = None
    transfer_reference: str | None = None
    qr_unavailable_reason: str | None = None

@dataclass(frozen=True)
class ManualReceipt:
    """An amount the Admin has verified receiving, not a team allocation."""
    payment_method: str
    amount: Decimal
    reference: str | None = None

class BookingBalancePort(Protocol):
    def get_booking_balance(self, actor: Actor, *, booking_id: int) -> BookingBalance: ...
    def confirm_booking_paid(self, actor: Actor, *, booking_id: int, expected_outstanding: Decimal,
                             idempotency_key: str, receipts: list[ManualReceipt]) -> BookingBalance: ...

@dataclass(frozen=True)
class PaymentApplyResult:
    payment_id: int
    booking_id: int
    applied: bool
    duplicate: bool
    late: bool

@dataclass(frozen=True)
class GatewayResult:
    state: str
    merchant_reference: str
    amount: Decimal
    currency: str = 'VND'
    provider_reference: str | None = None
    paid_at: datetime | None = None
    payment_url: str | None = None
    qr_payload: str | None = None
    expires_at: datetime | None = None

@dataclass(frozen=True)
class RefundPlan:
    booking_id: int
    cause: str
    items: list[dict] = field(default_factory=list)
    forfeited_payment_ids: list[int] = field(default_factory=list)

class BookingPort(Protocol):
    def create_match_hold(self, ctx, *, match_id: int, pitch_id: int, start_time: datetime,
                          end_time: datetime, source_user_id: int, opponent_user_id: int,
                          payment_rule: str) -> BookingHold: ...
