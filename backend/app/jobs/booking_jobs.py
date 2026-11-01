"""One-shot money workers; a scheduler calls them every 15 seconds. Each item owns its transaction,
and no lock is ever held across a gateway call."""
from dataclasses import replace
from flask import current_app
from sqlalchemy import select
from app.contracts.dto import GatewayResult
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import Booking, Payment
from app.services import booking_service, payment_service
from app.services.gateway import gateway_or_none
from app.use_cases.expire_hold import expire_booking_hold
from app.use_cases.process_payment import process_gateway_callback

def expire_holds():
    with UnitOfWork() as ctx:
        ids = list(ctx.session.scalars(select(Booking.booking_id).where(Booking.status == 'PENDING_HOLD', Booking.hold_expires_at <= ctx.now())))
    return sum(1 for booking_id in ids if expire_booking_hold(booking_id))

def _apply_refund(booking_id, verified):
    with UnitOfWork() as ctx:
        booking_service.lock_booking_graph(ctx, booking_id)
        payment_service.apply_verified_refund(ctx, verified)

def process_refunds():
    """Query before requesting, so a crash after the gateway call never sends a second refund."""
    with UnitOfWork() as ctx:
        rows = ctx.session.scalars(select(Payment).where(Payment.payment_type == 'REFUND', Payment.status == 'REFUND_PROCESSING')).all()
        work = []
        for refund in rows:
            original = ctx.session.get(Payment, refund.refund_for_payment_id)
            work.append((refund.booking_id, refund.payment_method, refund.transaction_code, original.transaction_code, refund.amount, original.created_at))
    settled = 0
    for booking_id, method, code, original_code, amount, paid_date in work:
        gateway = gateway_or_none(method)
        if gateway is None:
            continue  # CASH/BANK_TRANSFER wait for the Admin to hand the money back.
        try:
            result = gateway.query_refund(code, merchant_reference=original_code, amount=amount, transaction_date=paid_date)
            if result.state == 'NOT_FOUND':
                result = gateway.request_refund(original_code, code, amount, transaction_date=paid_date)
        except Exception as error:
            current_app.logger.warning('Refund adapter failed (%s)', type(error).__name__)
            continue
        if result.state in ('SUCCESS', 'FAILED'):
            _apply_refund(booking_id, result)
            settled += 1
    return settled

def _reconcile_pending():
    with UnitOfWork() as ctx:
        rows = ctx.session.execute(select(Payment, Booking).join(Booking, Booking.booking_id == Payment.booking_id).where(
            Payment.status == 'PENDING', Payment.payment_method.in_(('VNPAY', 'MOMO')))).all()
        now = ctx.now()
        # A session stays payable until the hold deadline; before that "not found" proves nothing.
        work = [(p.payment_method, p.transaction_code, p.amount, p.created_at) for p, b in rows
                if b.status != 'PENDING_HOLD' or now >= b.hold_expires_at]
    resolved = 0
    for method, code, amount, created_at in work:
        gateway = gateway_or_none(method)
        if gateway is None:
            continue
        try:
            result = gateway.query_payment(code, amount=amount, transaction_date=created_at)
        except Exception as error:
            current_app.logger.warning('Payment query failed (%s)', type(error).__name__)
            continue
        if result.state == 'NOT_FOUND':
            result = replace(result, state='FAILED')
        if result.state in ('SUCCESS', 'FAILED'):
            process_gateway_callback(method, result)
            resolved += 1
    return resolved

def _recover_expired_refunds():
    """Expired booking still holding money is enough evidence to recreate the missing refund safely."""
    with UnitOfWork() as ctx:
        ids = set(ctx.session.scalars(select(Payment.booking_id).join(Booking, Booking.booking_id == Payment.booking_id).where(
            Booking.status == 'EXPIRED', Payment.status == 'SUCCESS', Payment.payment_type == 'BOOKING_DEPOSIT')))
    created = 0
    for booking_id in sorted(ids):
        with UnitOfWork() as ctx:
            booking, payments = booking_service.lock_booking_graph(ctx, booking_id)
            if booking.status == 'EXPIRED':
                # Only originals with no refund row at all: a verified FAILED refund goes to Admin
                # reconciliation and must not be resent on every worker run.
                attempted = {p.refund_for_payment_id for p in payments if p.payment_type == 'REFUND'}
                missing = [p.payment_id for p in payments if p.payment_id not in attempted]
                plan = payment_service.plan_refunds(ctx, booking_id=booking_id, cause='HOLD_TIMEOUT', payment_ids=missing)
                created += len(payment_service.execute_refund_plan(ctx, plan, note='HOLD_TIMEOUT recovered'))
    return created

def reconcile_payments():
    return {'resolved_payments': _reconcile_pending(), 'recovered_refunds': _recover_expired_refunds()}

def register_booking_commands(app):
    import click

    @app.cli.command('expire-booking-holds')
    def expire_command():
        """Expire unpaid holds once; schedule externally every 15 seconds."""
        click.echo({'expired_holds': expire_holds()})

    @app.cli.command('process-refunds')
    def refund_command():
        """Send and settle gateway refunds once."""
        click.echo({'settled_refunds': process_refunds()})

    @app.cli.command('reconcile-payments')
    def reconcile_command():
        """Reconcile expired online sessions and recover missing refunds once."""
        click.echo(reconcile_payments())
