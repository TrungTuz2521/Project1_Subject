from flask import current_app
from app.models import Notification
from app.services.email_service import EMAIL_TYPES

def notify(ctx, user_ids, notification_type, title, content, proposal_id=None, match_id=None, allow_email=True):
    for user_id in sorted(set(user_ids)):
        ctx.session.add(Notification(user_id=user_id, notification_type=notification_type,
                                     title=title, content=content, proposal_id=proposal_id, match_id=match_id,
                                     delivery_channel='IN_APP', delivery_status='SENT', sent_at=ctx.now()))

        if allow_email and current_app.config.get('EMAIL_ENABLED') and notification_type in EMAIL_TYPES:
            # Same transaction as the business event; rollback removes both notifications.
            # No network call occurs here. Explicit NULL bypasses sent_at's model default.
            from sqlalchemy import null
            ctx.session.add(Notification(user_id=user_id, notification_type=notification_type,
                title=title, content=content, proposal_id=proposal_id, match_id=match_id,
                delivery_channel='EMAIL', delivery_status='PENDING', sent_at=null()))
