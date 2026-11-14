"""Production entry point: gunicorn wsgi:app --bind 0.0.0.0:$PORT

RUN_SCHEDULER_IN_WEB=true also runs the scheduler on a background thread of this process, for hosts with no
free worker (Render free). Run gunicorn with exactly one worker then, or every worker starts its own scheduler."""
import os
from app import create_app

app = create_app()


def _start_scheduler():
    from threading import Thread
    from time import sleep
    from app.jobs.scheduler import run_forever

    def loop():
        while True:
            try:
                with app.app_context():
                    run_forever(15, with_matchmaking=True, with_email=app.config['EMAIL_ENABLED'],
                                echo=print)
            except Exception as error:  # A crash must not stop the jobs for good; retry after a pause.
                app.logger.error('In-process scheduler stopped (%s); restarting in 30s', type(error).__name__)
                sleep(30)

    Thread(target=loop, name='scheduler', daemon=True).start()


if os.getenv('RUN_SCHEDULER_IN_WEB', 'false').lower() == 'true':
    _start_scheduler()
