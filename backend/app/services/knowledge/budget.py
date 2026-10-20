"""Persistent, conservative reservations for paid model calls.

Reserve before sending. Ambiguous failures retain their reservation, preventing
retries or concurrent workers from silently exceeding the configured allowance.
Rates must be supplied from a verified pricing configuration.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from uuid import uuid4


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenRates:
    input_per_million_cny: Decimal
    output_per_million_cny: Decimal

    def __post_init__(self):
        for rate in (self.input_per_million_cny, self.output_per_million_cny):
            if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
                raise ValueError("rates must be positive finite Decimal values")

    def micro_cny(self, input_tokens: int, output_tokens: int) -> int:
        for count in (input_tokens, output_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("token counts must be nonnegative integers")
        # One yuan is one million micro-yuan, cancelling the per-million divisor.
        return int((self.input_per_million_cny * input_tokens +
                    self.output_per_million_cny * output_tokens).to_integral_value(rounding=ROUND_CEILING))


class BudgetLedger:
    def __init__(self, path: Path, limit_cny: Decimal):
        if not isinstance(limit_cny, Decimal) or not limit_cny.is_finite() or limit_cny <= 0:
            raise ValueError("budget limit must be a positive finite Decimal")
        self.path = Path(path)
        self.limit = int((limit_cny * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS model_budget (
                id TEXT PRIMARY KEY, model TEXT NOT NULL, reserved INTEGER NOT NULL,
                actual INTEGER, state TEXT NOT NULL DEFAULT 'reserved',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (reserved >= 0), CHECK (actual IS NULL OR actual >= 0)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS model_budget_control (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), halted INTEGER NOT NULL
            )""")
            conn.execute("INSERT OR IGNORE INTO model_budget_control VALUES(1,0)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, model: str, input_bound: int, output_bound: int, rates: TokenRates) -> str:
        if not model or not isinstance(model, str):
            raise ValueError("model is required")
        amount = rates.micro_cny(input_bound, output_bound)
        key = str(uuid4())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT halted FROM model_budget_control WHERE singleton=1").fetchone()[0]:
                raise BudgetExceeded("model budget halted after provider usage exceeded its reservation")
            used = conn.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM model_budget").fetchone()[0]
            if used + amount > self.limit:
                raise BudgetExceeded("model call exceeds the remaining API budget")
            conn.execute("INSERT INTO model_budget(id,model,reserved) VALUES(?,?,?)", (key, model, amount))
        return key

    def settle(self, reservation: str, input_tokens: int, output_tokens: int, rates: TokenRates) -> None:
        amount = rates.micro_cny(input_tokens, output_tokens)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT reserved,state FROM model_budget WHERE id=?", (reservation,)).fetchone()
            if row is None:
                raise ValueError("unknown reservation")
            if row[1] != "reserved":
                raise ValueError("reservation was already settled")
            conn.execute("UPDATE model_budget SET actual=?,state='settled' WHERE id=?", (amount, reservation))
            if amount > row[0]:
                conn.execute("UPDATE model_budget_control SET halted=1 WHERE singleton=1")
        if amount > row[0]:
            raise RuntimeError("provider usage exceeded the reserved bound; stop calls and inspect pricing")

    def summary(self) -> dict:
        with self._connect() as conn:
            charged, pending, count = conn.execute("""SELECT
                COALESCE(SUM(actual),0),
                COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0),
                COUNT(*) FROM model_budget""").fetchone()
        return {"limit_cny": str(Decimal(self.limit) / 1_000_000),
                "accounted_cny": str(Decimal(charged) / 1_000_000),
                "pending_reserved_cny": str(Decimal(pending) / 1_000_000), "calls": count}
