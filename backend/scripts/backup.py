"""Back up the database and the attachment bucket into one archive.

Run inside the backend container, or anywhere `DATABASE_URL` and the `S3_*`
settings point at the live services:

    python scripts/backup.py                    # into ./backups
    python scripts/backup.py --out /srv/backups
    python scripts/backup.py --keep 14          # prune older sets

**Both stores or neither.** A ticket's attachments are half in Postgres — the
row, its filename, its checksum — and half in object storage, which holds the
bytes. Backing up only the database produces a restore where every attachment
lists correctly and fails on download, which is worse than an obvious outage
because it looks healthy. So each backup is a directory containing the dump and
the objects, and the restore refuses a set that is missing either.

**The dump is taken first, objects second.** An attachment row committed during
the run would otherwise point at an object the sweep had already passed. Taking
the database first means the worst case is an extra object with no row — which
restores harmlessly — rather than a row with no object.

`pg_dump --format=custom` because it restores selectively and in parallel, and
because `pg_restore` can list its contents, which is what makes the manifest
below checkable rather than aspirational.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

#: Written into every backup directory. `restore.py` reads it back and refuses
#: anything it does not recognise.
MANIFEST_NAME = "manifest.json"
DUMP_NAME = "database.dump"
OBJECTS_DIR = "objects"


def _pg_dump_url() -> str:
    """`postgresql://` — asyncpg's URL scheme is not one libpq understands."""
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def dump_database(target: Path) -> int:
    """pg_dump into `target`. Returns the file size in bytes."""
    result = subprocess.run(  # noqa: S603 - args come from settings, not input
        [  # noqa: S607 - PATH lookup: the binary moves between container and host
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file", str(target),
            _pg_dump_url(),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
    return target.stat().st_size


def copy_objects(target_dir: Path) -> tuple[int, int]:
    """Download every object in the bucket. Returns (count, total bytes).

    Keys are stored as a flat file per object with the key recorded in the
    manifest, rather than recreating the `tickets/<id>/<uuid>` tree on disk:
    a key is opaque and may contain characters a filesystem will not take.
    """
    client = _s3_client()
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except Exception as exc:
        raise RuntimeError(
            f"Attachment bucket '{settings.S3_BUCKET}' is unreachable: {exc}. "
            "Refusing to write a database-only backup — see this file's docstring."
        ) from exc

    entries: list[dict] = []
    total = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.S3_BUCKET):
        for item in page.get("Contents", []):
            key = item["Key"]
            # A stable, filesystem-safe local name derived from the key, so a
            # restore can put every object back exactly where it came from.
            local = hashlib.sha256(key.encode()).hexdigest()
            client.download_file(settings.S3_BUCKET, key, str(target_dir / local))
            size = (target_dir / local).stat().st_size
            entries.append({"key": key, "file": local, "size_bytes": size})
            total += size

    (target_dir / "index.json").write_text(json.dumps(entries, indent=1))
    return len(entries), total


async def row_counts() -> dict[str, int]:
    """Counts for the tables a restore is checked against."""
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.attachment import Attachment
    from app.models.comment import TicketComment
    from app.models.ticket import Ticket
    from app.models.user import User

    async with SessionLocal() as db:
        counts = {}
        for name, model in (
            ("users", User),
            ("tickets", Ticket),
            ("comments", TicketComment),
            ("attachments", Attachment),
        ):
            counts[name] = (await db.execute(select(func.count(model.id)))).scalar_one()
    return counts


def prune(root: Path, keep: int) -> list[str]:
    """Drop all but the newest `keep` backup sets."""
    sets = sorted(
        (p for p in root.iterdir() if p.is_dir() and (p / MANIFEST_NAME).exists()),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = []
    for old in sets[keep:]:
        shutil.rmtree(old)
        removed.append(old.name)
    return removed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.environ.get("BACKUP_DIR", "./backups"))
    parser.add_argument(
        "--keep", type=int, default=0,
        help="Delete all but the newest N sets after a successful backup.",
    )
    args = parser.parse_args()

    root = Path(args.out).expanduser().resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = root / stamp
    target.mkdir(parents=True, exist_ok=False)

    print(f"[backup] {target}")

    try:
        counts = await row_counts()
        print(f"  [backup] rows: {counts}")

        dump_bytes = dump_database(target / DUMP_NAME)
        print(f"  [backup] database.dump  {dump_bytes:,} bytes")

        object_count, object_bytes = copy_objects(target / OBJECTS_DIR)
        print(f"  [backup] objects        {object_count} files, {object_bytes:,} bytes")
    except Exception as exc:
        # A partial set is worse than none: it would restore quietly and be
        # wrong. Remove it so the newest surviving set is one that completed.
        shutil.rmtree(target, ignore_errors=True)
        print(f"  [backup] FAILED, incomplete set removed: {exc}", file=sys.stderr)
        return 1

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "database_url_host": _pg_dump_url().rsplit("@", 1)[-1],  # no credentials
        "bucket": settings.S3_BUCKET,
        "dump_bytes": dump_bytes,
        "object_count": object_count,
        "object_bytes": object_bytes,
        "row_counts": counts,
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))

    if args.keep > 0:
        for name in prune(root, args.keep):
            print(f"  [backup] pruned {name}")

    print(f"[backup] done — restore with: python scripts/restore.py {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
