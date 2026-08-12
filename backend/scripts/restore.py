"""Restore a backup set produced by `backup.py`.

    python scripts/restore.py backups/20260811T020304Z --yes

**This destroys the current database.** `pg_restore --clean` drops every object
it is about to recreate, so the target is whatever the dump held and nothing
else. The confirmation prompt is the guard; `--yes` skips it for automation.

The restore goes database first, then objects, and **verifies before declaring
success**: row counts are compared against the manifest, and every attachment
row is checked to have its object present in the bucket. A restore that leaves
rows pointing at missing files is the specific failure this pair exists to
prevent, so it is checked rather than assumed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from scripts.backup import (
    DUMP_NAME,
    MANIFEST_NAME,
    OBJECTS_DIR,
    _pg_dump_url,
    _s3_client,
    row_counts,
)


def restore_database(dump: Path) -> None:
    result = subprocess.run(  # noqa: S603 - args come from settings, not input
        [  # noqa: S607 - PATH lookup: the binary moves between container and host
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--dbname", _pg_dump_url(),
            str(dump),
        ],
        capture_output=True,
        text=True,
    )
    # pg_restore reports a non-zero status for warnings too — most commonly
    # "does not exist, skipping" from --clean against a fresh database. Those
    # are expected; anything containing "error:" is not.
    errors = [ln for ln in result.stderr.splitlines() if "error:" in ln.lower()]
    if errors:
        raise RuntimeError("pg_restore failed:\n" + "\n".join(errors[:20]))


def restore_objects(objects_dir: Path) -> int:
    index = json.loads((objects_dir / "index.json").read_text())
    client = _s3_client()

    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except Exception:
        client.create_bucket(Bucket=settings.S3_BUCKET)

    for entry in index:
        client.upload_file(
            str(objects_dir / entry["file"]), settings.S3_BUCKET, entry["key"]
        )
    return len(index)


async def verify(manifest: dict) -> list[str]:
    """Return a list of problems; empty means the restore is sound."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.attachment import Attachment

    problems: list[str] = []

    actual = await row_counts()
    for table, expected in manifest["row_counts"].items():
        if actual.get(table) != expected:
            problems.append(
                f"{table}: expected {expected} rows, found {actual.get(table)}"
            )

    # The check that matters: every attachment row must have its bytes back.
    client = _s3_client()
    async with SessionLocal() as db:
        rows = (await db.execute(select(Attachment))).scalars().all()

    missing = []
    for row in rows:
        try:
            client.head_object(Bucket=row.s3_bucket, Key=row.s3_key)
        except Exception:
            missing.append(row.original_filename)
    if missing:
        problems.append(
            f"{len(missing)} attachment(s) have no object in storage: "
            + ", ".join(missing[:5])
        )

    return problems


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation.")
    args = parser.parse_args()

    source = Path(args.backup_dir).expanduser().resolve()
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"[restore] {source} has no {MANIFEST_NAME} — not a backup set.", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    dump = source / DUMP_NAME
    objects_dir = source / OBJECTS_DIR

    # Refuse a half set rather than restore a database whose attachments are
    # gone — see the module docstring in backup.py.
    if not dump.exists():
        print(f"[restore] {DUMP_NAME} missing from the set.", file=sys.stderr)
        return 1
    if not (objects_dir / "index.json").exists():
        print(f"[restore] {OBJECTS_DIR}/index.json missing from the set.", file=sys.stderr)
        return 1

    print(f"[restore] set taken {manifest['created_at']}")
    print(f"  rows    : {manifest['row_counts']}")
    print(f"  objects : {manifest['object_count']}")
    print(f"  target  : {_pg_dump_url().rsplit('@', 1)[-1]}, bucket {settings.S3_BUCKET}")

    if not args.yes:
        print("\nThis REPLACES the target database and bucket contents.")
        if input("Type 'restore' to continue: ").strip() != "restore":
            print("[restore] aborted.")
            return 1

    restore_database(dump)
    print("  [restore] database restored")

    count = restore_objects(objects_dir)
    print(f"  [restore] {count} objects restored")

    problems = await verify(manifest)
    if problems:
        print("[restore] VERIFICATION FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("[restore] verified — row counts match and every attachment has its bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
