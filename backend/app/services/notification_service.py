from app.models import Notification

def notify(ctx, user_ids, notification_type, title, content, proposal_id=None, match_id=None):
    for user_id in sorted(set(user_ids)):
        ctx.session.add(Notification(user_id=user_id, notification_type=notification_type,
                                     title=title, content=content, proposal_id=proposal_id, match_id=match_id,
                                     delivery_channel='IN_APP', delivery_status='SENT', sent_at=ctx.now()))
