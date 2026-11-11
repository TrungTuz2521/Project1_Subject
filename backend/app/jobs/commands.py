import click
from sqlalchemy import select
from app.infrastructure.unit_of_work import UnitOfWork
from app.models import MatchPost, MatchProposal, ProposalConfirmation, Team
from app.services import matchmaking_service as mm, notification_service
from app.contracts.errors import DomainError

def scan_open_posts(post_id=None):
    # Each candidate pair owns its transaction. Never lock an entire scan batch.
    with UnitOfWork() as ctx:
        query = select(MatchPost).where(MatchPost.status == 'OPEN', MatchPost.expiry_time > ctx.now()).order_by(MatchPost.created_at, MatchPost.post_id)
        rows = list(ctx.session.scalars(query))
        sources = [p for p in rows if post_id is None or p.post_id == post_id]
        candidates = {p.post_id: sorted([(mm.score(ctx, p, t), t.created_at, t.post_id) for t in rows if t.post_id != p.post_id],
                                      key=lambda x: (-x[0], x[1], x[2])) for p in sources}
    ids = []
    for source_id, targets in candidates.items():
        for points, _, target_id in targets:
            if points < 80:
                break
            with UnitOfWork() as ctx:
                proposal = mm.scan_pair(ctx, source_id, target_id)
                if proposal:
                    ids.append(proposal.proposal_id)
                    break
    return {'scanned_count': len(sources), 'created_proposal_ids': ids}

def expire_proposals():
    with UnitOfWork() as ctx:
        ids = list(ctx.session.scalars(select(MatchProposal.proposal_id).where(
            MatchProposal.status == 'PENDING_CONFIRMATION', MatchProposal.expires_at <= ctx.now())))
    count = 0
    for proposal_id in ids:
        with UnitOfWork() as ctx:
            proposal = ctx.session.get(MatchProposal, proposal_id)
            posts = [ctx.session.get(MatchPost, pid) for pid in (proposal.source_post_id, proposal.target_post_id) if pid]
            ctx.locks.lock(Team, [p.team_id for p in posts])
            ctx.locks.lock(MatchPost, [p.post_id for p in posts])
            ctx.locks.lock(MatchProposal, [proposal_id])
            if proposal.status == 'PENDING_CONFIRMATION' and proposal.expires_at <= ctx.now():
                proposal.status = 'EXPIRED'
                mm.reopen(ctx, posts)
                confirmations = ctx.session.scalars(select(ProposalConfirmation).where(ProposalConfirmation.proposal_id == proposal_id))
                notification_service.notify(ctx, [c.user_id for c in confirmations], 'PROPOSAL_EXPIRED',
                    'Đề xuất hết hạn', 'Đề xuất chưa được hai bên xác nhận đúng hạn.', proposal_id=proposal_id)
                count += 1
    with UnitOfWork() as ctx:
        post_ids = list(ctx.session.scalars(select(MatchPost.post_id).where(MatchPost.status == 'OPEN', MatchPost.expiry_time <= ctx.now())))
    for post_id in post_ids:
        with UnitOfWork() as ctx:
            post = ctx.session.get(MatchPost, post_id)
            ctx.locks.lock(Team, [post.team_id])
            ctx.locks.lock(MatchPost, [post_id])
            if post.status == 'OPEN' and post.expiry_time <= ctx.now():
                post.status = 'EXPIRED'
                notification_service.notify(ctx, [post.creator_id], 'POST_EXPIRED', 'Bài đăng hết hạn', 'Bài đã hết thời gian tìm kiếm.')
    return count

def register_commands(app):
    @app.cli.command('scan-matchmaking')
    def scan_command():
        """Run one matchmaking scan; schedule externally every 15 seconds."""
        click.echo(scan_open_posts())

    @app.cli.command('matchmaking-worker')
    @click.option('--interval', default=15, show_default=True, type=click.IntRange(1, 300))
    def matchmaking_worker_command(interval):
        """Continuously scan open posts; default interval 15 seconds. Stop with Ctrl+C."""
        from app.jobs.matchmaking_worker import run_matchmaking_worker
        run_matchmaking_worker(interval)

    @app.cli.command('expire-proposals')
    def expire_command():
        """Expire proposals/posts; booking expiry is owned by Tú."""
        click.echo({'expired_proposals': expire_proposals()})

    @app.cli.command('scheduler')
    @click.option('--interval', default=15, show_default=True, type=click.IntRange(5, 300))
    @click.option('--with-matchmaking', is_flag=True, help='Also scan open posts (replaces matchmaking-worker).')
    @click.option('--with-email', is_flag=True, help='Also send pending emails (replaces email-worker).')
    @click.option('--once', is_flag=True, help='Run every job a single time and exit.')
    def scheduler_command(interval, with_matchmaking, with_email, once):
        """Run all periodic jobs: proposal/hold expiry, payment reconciliation, refunds, match completion."""
        from app.jobs.scheduler import run_forever, run_once
        if once:
            click.echo(run_once(with_matchmaking, with_email))
            return
        run_forever(interval, with_matchmaking, with_email, echo=click.echo)

    @app.cli.command('create-admin')
    @click.option('--email', required=True, help='Admin login email.')
    @click.option('--name', default='Quan tri vien', show_default=True, help='Display name (new accounts only).')
    @click.option('--password', prompt='Mat khau (8-72 ky tu)', hide_input=True, confirmation_prompt='Nhap lai mat khau',
                  help='Omit to type it hidden; avoid passing it on the command line.')
    def create_admin_command(email, name, password):
        """Create an ADMIN account, or promote an existing account by email and set its password."""
        import bcrypt
        from app.contracts.errors import DomainError
        from app.models import User
        from app.utils import validation as v
        try:
            address = v.email(email)
            full_name = v.text(name, 'full_name', 100, 2)
        except DomainError as error:
            raise click.ClickException(f'Du lieu khong hop le: {list(error.fields) or error.code}')
        if not 8 <= len(password.encode('utf-8')) <= 72:
            raise click.ClickException('Mat khau phai dai 8-72 byte UTF-8.')
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()
        with UnitOfWork() as ctx:
            user = ctx.session.scalar(select(User).where(User.email == address))
            if user is None:
                user = User(full_name=full_name, email=address, password_hash=hashed, role='ADMIN', status='ACTIVE')
                ctx.session.add(user)
                ctx.session.flush()
                action = 'Da tao'
            else:
                # Changing role and password also revokes every token this account held before.
                user.role, user.status, user.password_hash = 'ADMIN', 'ACTIVE', hashed
                action = 'Da nang quyen ADMIN va dat lai mat khau cho'
            user_id = user.user_id
        click.echo(f'{action} tai khoan #{user_id} <{address}>. Dang nhap bang email nay va mat khau vua nhap.')

    @app.cli.command('complete-matches')
    def complete_matches_command():
        """Mark confirmed matches whose booking has ended as COMPLETED, once."""
        from app.services.match_service import complete_finished_matches
        click.echo({'completed_matches': complete_finished_matches()})

    @app.cli.command('check-email')
    def check_email_command():
        """Verify SMTP authentication only; never sends an email."""
        from app.services.email_service import check_connection
        try:
            check_connection()
        except Exception as error:
            raise click.ClickException('SMTP connection/authentication failed (' + type(error).__name__ + ').')
        click.echo('SMTP authentication successful. No email sent.')

    @app.cli.command('send-pending-emails')
    @click.option('--limit', default=50, type=click.IntRange(1, 500))
    def send_emails_command(limit):
        """Process a single batch of PENDING email notifications."""
        from app.services.email_service import process_emails
        click.echo(process_emails(limit))

    @app.cli.command('email-worker')
    @click.option('--interval', default=10, type=click.IntRange(1, 300))
    def email_worker_command(interval):
        """Continuously deliver new notification emails; stop with Ctrl+C."""
        from time import sleep
        from app.services.email_service import process_emails, smtp_settings
        smtp_settings()
        click.echo('Email worker running; Ctrl+C to stop.')
        while True:
            try:
                stats = process_emails()
                if any(stats.values()):
                    click.echo(stats)
            except Exception as error:
                app.logger.warning('Email worker batch failed (%s)', type(error).__name__)
            sleep(interval)

    @app.cli.command('check-db')
    def check_db():
        """Read-only connectivity + mapped-column audit. Never runs migrations."""
        from sqlalchemy import inspect, text
        from app.extensions import db
        with db.engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            inspector = inspect(connection)
            missing = []
            for table in db.metadata.sorted_tables:
                if not inspector.has_table(table.name):
                    missing.append(table.name)
                    continue
                actual = {c['name'] for c in inspector.get_columns(table.name)}
                missing.extend(f'{table.name}.{c.name}' for c in table.columns if c.name not in actual)
        if missing:
            raise click.ClickException('Missing mapped columns: ' + ', '.join(missing))
        click.echo('Database reachable; all mapped columns present. No changes made.')
