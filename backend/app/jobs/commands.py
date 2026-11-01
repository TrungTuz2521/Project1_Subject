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

    @app.cli.command('expire-proposals')
    def expire_command():
        """Expire proposals/posts; booking expiry is owned by Tú."""
        click.echo({'expired_proposals': expire_proposals()})

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
