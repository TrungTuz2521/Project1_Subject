"""Run matchmaking scans sequentially; no database transaction survives between ticks."""
from time import monotonic, sleep
import click
from flask import current_app
from app.jobs.commands import scan_open_posts


def run_matchmaking_worker(interval=15):
    click.echo(f'Matchmaking worker running every {interval}s; Ctrl+C to stop.')
    while True:
        started = monotonic()
        try:
            result = scan_open_posts()
            click.echo(result)
        except Exception as error:
            # Keep running after a failed tick; never log SQL, credentials or payloads.
            current_app.logger.warning('Matchmaking scan failed (%s); will retry next tick.', type(error).__name__)
        # Start-to-start cadence when scans finish within the interval. Slow scans never overlap.
        sleep(max(0, interval - (monotonic() - started)))
