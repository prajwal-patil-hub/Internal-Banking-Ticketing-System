"""Background worker package.

Exports setup and shutdown functions for all APScheduler workers so that
app.main can wire them into the FastAPI lifespan context manager.
"""

from app.workers.email_worker import setup_email_worker, shutdown_email_worker
from app.workers.sla_worker import setup_sla_worker, shutdown_sla_worker

__all__ = [
    "setup_email_worker",
    "setup_sla_worker",
    "shutdown_email_worker",
    "shutdown_sla_worker",
]
