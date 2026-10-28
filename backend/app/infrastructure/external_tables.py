"""Read/lock external tables without creating duplicate ORM models owned by Tú."""
from sqlalchemy import text
from app.contracts.enums import LOCK_ORDER

def lock_pitch(ctx, pitch_id):
    key = (LOCK_ORDER.index('pitches'), pitch_id)
    if key not in ctx.locks.held:
        if key < ctx.locks.last:
            raise RuntimeError('Pitch must be locked before posts')
        ctx.locks.last = key
        ctx.locks.held.add(key)
    suffix = '' if ctx.session.bind.dialect.name == 'sqlite' else ' FOR UPDATE'
    return ctx.session.execute(text('SELECT pitch_id FROM pitches WHERE pitch_id=:id' + suffix), {'id': pitch_id}).first()
