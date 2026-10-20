from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from app.services.knowledge.budget import BudgetExceeded, BudgetLedger, TokenRates

RATES = TokenRates(Decimal('2'), Decimal('8'))


def test_budget_reserves_before_usage_and_retains_unknown_failures(tmp_path):
    ledger = BudgetLedger(tmp_path / 'usage.sqlite3', Decimal('0.001'))
    key = ledger.reserve('test', 100, 100, RATES)
    with pytest.raises(BudgetExceeded):
        ledger.reserve('test', 1, 1, RATES)
    ledger.settle(key, 10, 10, RATES)
    assert ledger.summary()['accounted_cny'] == '0.0001'
    assert ledger.summary()['pending_reserved_cny'] == '0'
    with pytest.raises(ValueError):
        ledger.settle(key, 10, 10, RATES)


def test_concurrent_reservations_do_not_overspend(tmp_path):
    ledger = BudgetLedger(tmp_path / 'usage.sqlite3', Decimal('0.001'))

    def reserve(_):
        try:
            return ledger.reserve('test', 100, 0, RATES)
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(20)))
    assert sum(value is not None for value in results) == 5
    assert ledger.summary()['pending_reserved_cny'] == '0.001'


def test_restart_preserves_reservations(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    BudgetLedger(path, Decimal('0.001')).reserve('test', 100, 100, RATES)
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path, Decimal('0.001')).reserve('test', 1, 1, RATES)


def test_provider_overrun_halts_future_calls_across_restart(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    ledger = BudgetLedger(path, Decimal('50'))
    key = ledger.reserve('test', 1, 1, RATES)
    with pytest.raises(RuntimeError):
        ledger.settle(key, 100, 100, RATES)
    assert ledger.summary()['accounted_cny'] == '0.001'
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path, Decimal('50')).reserve('test', 1, 1, RATES)


@pytest.mark.parametrize('value', [Decimal('NaN'), Decimal('Infinity'), Decimal('-1'), Decimal('0')])
def test_invalid_rates_rejected(value):
    with pytest.raises(ValueError):
        TokenRates(value, Decimal('8'))
