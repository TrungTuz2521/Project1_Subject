"""One process that runs every periodic job, so expiry, refunds, QR cleanup and match completion
happen without someone typing each command. Each job owns its transactions; one failing job never
stops the others or the loop."""
from time import monotonic, sleep
from flask import current_app


def _jobs(with_matchmaking, with_email):
    from app.jobs.booking_jobs import expire_holds, process_refunds, reconcile_payments
    from app.jobs.commands import expire_proposals, scan_open_posts
    from app.services.match_service import complete_finished_matches
    jobs = [('expire_proposals', expire_proposals), ('expire_holds', expire_holds),
            ('reconcile_payments', reconcile_payments), ('process_refunds', process_refunds),
            ('complete_matches', complete_finished_matches)]
    if with_matchmaking:
        jobs.append(('matchmaking', scan_open_posts))
    if with_email:
        from app.services.email_service import process_emails
        jobs.append(('emails', process_emails))
    return jobs


def _worth_logging(result):
    if isinstance(result, dict):
        return any(_worth_logging(value) for value in result.values())
    if isinstance(result, (list, tuple)):
        return bool(result)
    return bool(result) and not isinstance(result, bool)


def run_once(with_matchmaking=False, with_email=False):
    """Returns {job: result or 'ERROR <type>'}."""
    results = {}
    for name, job in _jobs(with_matchmaking, with_email):
        try:
            results[name] = job()
        except Exception as error:
            current_app.logger.warning('Scheduled job %s failed (%s)', name, type(error).__name__)
            results[name] = f'ERROR {type(error).__name__}'
    return results


def run_forever(interval, with_matchmaking=False, with_email=False, echo=print):
    if with_email:
        from app.services.email_service import smtp_settings
        smtp_settings()  # Fail fast on missing SMTP config instead of logging it every tick.
    echo(f'Scheduler running every {interval}s; Ctrl+C to stop.')
    while True:
        started = monotonic()
        results = run_once(with_matchmaking, with_email)
        changed = {k: v for k, v in results.items() if _worth_logging(v)}
        if changed:
            echo(changed)
        sleep(max(interval - (monotonic() - started), 1))
