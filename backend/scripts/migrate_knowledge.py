"""Explicit additive knowledge migration runner; never imported by app startup.

Usage (first use a disposable/backup-restored PostgreSQL with pgvector installed):
    KNOWLEDGE_DATABASE_URL=postgresql://... python backend/scripts/migrate_knowledge.py
    python backend/scripts/migrate_knowledge.py --list

DSNs are read only from the named environment variable, never .env or application
settings. Paths are anchored to backend/, independent of the process CWD. One
transaction and a transaction-scoped advisory lock protect bootstrap, checksums,
DDL and schema_migrations records together. A failed extension/DDL rolls back all
changes. Completed migrations with modified bytes fail instead of being replayed.
No down migration or changes to the existing application tables are provided.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sys

import psycopg
from psycopg import AsyncConnection


MIGRATION_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations" / "knowledge"
MIGRATION_LOCK = 64197233001


class MigrationError(RuntimeError):
    """Actionable migration error whose message does not contain the DSN."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    filename: str
    checksum: str
    sql: str


def discover_migrations(directory: Path = MIGRATION_DIRECTORY) -> tuple[Migration, ...]:
    """Read a strictly numbered SQL series and checksum exact UTF-8 file bytes."""
    migrations = []
    versions = set()
    if not directory.is_dir():
        raise MigrationError("knowledge migration directory does not exist")
    for path in sorted(directory.glob("*.sql")):
        match = re.fullmatch(r"([0-9]{3})_[a-z0-9_]+\.sql", path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = match.group(1)
        if version in versions:
            raise MigrationError(f"duplicate migration version: {version}")
        versions.add(version)
        content = path.read_bytes()
        sql = content.decode("utf-8")
        if not sql.strip():
            raise MigrationError(f"empty migration: {path.name}")
        migrations.append(Migration(version, path.name, hashlib.sha256(content).hexdigest(), sql))
    if not migrations:
        raise MigrationError("no knowledge SQL migrations found")
    return tuple(migrations)


def pending_migrations(migrations: tuple[Migration, ...],
                       applied: dict[str, tuple[str, str]]) -> tuple[Migration, ...]:
    """Reject checksum/name drift, missing historical files and out-of-order additions."""
    known = {migration.version: migration for migration in migrations}
    for version, (filename, checksum) in applied.items():
        local = known.get(version)
        if local is None or (local.filename, local.checksum) != (filename, checksum):
            raise MigrationError(f"applied migration {version} is missing or its name/checksum changed")
    pending = tuple(migration for migration in migrations if migration.version not in applied)
    if applied and any(migration.version < max(applied) for migration in pending):
        raise MigrationError("cannot insert migrations before the latest applied version")
    return pending


async def migrate(connection: AsyncConnection,
                  migrations: tuple[Migration, ...] | None = None) -> tuple[str, ...]:
    """Apply on caller's idle autocommit connection, returning newly applied names."""
    if not connection.autocommit or connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise MigrationError("migration requires an idle autocommit connection")
    entries = discover_migrations() if migrations is None else migrations
    completed = []
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        await connection.execute("CREATE SCHEMA IF NOT EXISTS knowledge")
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS knowledge.schema_migrations (
                version text PRIMARY KEY,
                filename text NOT NULL UNIQUE,
                checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
            """)
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT version,filename,checksum FROM knowledge.schema_migrations")
            applied = {version: (filename, checksum) for version, filename, checksum in await cursor.fetchall()}
        for migration in pending_migrations(entries, applied):
            try:
                # No parameters: psycopg's simple-query mode handles PL/pgSQL bodies
                # and multi-statement SQL intact. All DDL identifiers are checked-in.
                await connection.execute(migration.sql, prepare=False)
            except psycopg.Error as exc:
                if not completed and migration.version == "001":
                    raise MigrationError(
                        "knowledge 001 failed (SQLSTATE " + (exc.sqlstate or "unknown") + "). "
                        "Ensure pgvector is installed on the PostgreSQL server, vector is in the public "
                        "schema, and the migration role can CREATE EXTENSION/SCHEMA/TABLE/FUNCTION. "
                        "CREATE EXTENSION failures are fatal; the transaction was rolled back. "
                        "PostgreSQL: " + (exc.diag.message_primary or "no server diagnostic")
                    ) from exc
                raise MigrationError(f"knowledge migration {migration.filename} failed; transaction rolled back") from exc
            await connection.execute("""
                INSERT INTO knowledge.schema_migrations(version,filename,checksum) VALUES (%s,%s,%s)
                """, (migration.version, migration.filename, migration.checksum))
            completed.append(migration.filename)
    return tuple(completed)


async def _run(dsn: str) -> tuple[str, ...]:
    # psycopg does not accept SQLAlchemy's +asyncpg driver scheme.
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise MigrationError("DSN must use postgresql:// or postgres://")
    async with await AsyncConnection.connect(dsn, autocommit=True, connect_timeout=10) as connection:
        return await migrate(connection)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list local checksums without connecting")
    parser.add_argument("--dsn-env", default="KNOWLEDGE_DATABASE_URL", help="environment variable holding an explicit migration DSN")
    args = parser.parse_args(argv)
    try:
        if args.list:
            for migration in discover_migrations():
                print(f"{migration.filename} {migration.checksum}")
            return 0
        dsn = os.environ.get(args.dsn_env, "")
        if not dsn:
            raise MigrationError(f"set {args.dsn_env} explicitly; no database was contacted")
        # psycopg async requires SelectorEventLoop on Windows, not Proactor.
        if sys.platform == "win32":
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                completed = runner.run(_run(dsn))
        else:
            completed = asyncio.run(_run(dsn))
        print("Applied: " + ", ".join(completed) if completed else "Knowledge schema already up to date")
        return 0
    except MigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        # Don't print connection exceptions: some include supplied connection details.
        print(f"PostgreSQL migration connection/transaction failed (SQLSTATE {exc.sqlstate or 'unknown'}); "
              "check connectivity and credentials. No DSN is logged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
