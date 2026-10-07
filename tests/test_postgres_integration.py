"""Opt-in integration on an explicitly supplied isolated test DB, never production."""

import os
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.platform import Platform
from backend.shared.contracts import OrderIntent, Side, Tick
from backend.shared.postgres import PostgresStore


@pytest.mark.skipif(
    not os.getenv("ALGOSHIELD_TEST_DATABASE_URL"),
    reason="isolated PostgreSQL test database not configured",
)
def test_postgres_fill_reservation_recovery():
    store = PostgresStore(os.environ["ALGOSHIELD_TEST_DATABASE_URL"])
    p = Platform(store=store)
    key = "test-" + str(uuid4())
    try:
        # Rollback-only test, including audits and nested service transactions.
        class Rollback(Exception):
            pass

        with pytest.raises(Rollback):
            with store.transaction():
                p.account(key)
                p.strategies.subscribe(key, key, "momentum", "TEST")
                p.tick(Tick("TEST", int(p.clock()), Decimal("100"), 0, key))
                p.reliability.resume()
                intent = OrderIntent(key, key, key, "TEST", Side.BUY, 100, p.clock())
                assert p.risk.submit(intent).allowed
                f = p.broker.execute(key, 40, Decimal("100"), p.clock())
                assert p.ingest(f)
                assert not p.ingest(f)
                assert p.ledger.quantity(key, key, "TEST") == 40
                assert p.reliability.reconcile()
                assert p.kill().status == "SUCCESS"
                raise Rollback()
        assert not store.rows("SELECT id FROM accounts WHERE id=?", (key,))
    finally:
        store.close()
