from backend.shared.contracts import AccountRiskPolicy


class AccountPolicyRepository:
    """Durable account-level net and gross exposure limits."""

    def __init__(self, store):
        self.store = store

    def get(self, account):
        rows = self.store.rows(
            "SELECT * FROM account_risk_policies WHERE account=?", (account,)
        )
        if not rows:
            return AccountRiskPolicy()
        row = rows[0]
        return AccountRiskPolicy(
            row["max_net_position_per_symbol"],
            row["max_gross_virtual_position_per_symbol"],
        )

    def set(self, account, policy):
        if not isinstance(policy, AccountRiskPolicy):
            raise ValueError("canonical AccountRiskPolicy required")
        with self.store.transaction() as db:
            if not db.execute(
                "SELECT id FROM accounts WHERE id=?", (account,)
            ).fetchone():
                raise ValueError("account does not exist")
            db.execute(
                "INSERT INTO account_risk_policies VALUES (?,?,?) "
                "ON CONFLICT(account) DO UPDATE SET "
                "max_net_position_per_symbol=excluded.max_net_position_per_symbol,"
                "max_gross_virtual_position_per_symbol=excluded.max_gross_virtual_position_per_symbol",
                (
                    account,
                    policy.max_net_position_per_symbol,
                    policy.max_gross_virtual_position_per_symbol,
                ),
            )
            self.store.audit(
                "ACCOUNT_RISK_POLICY_UPDATED",
                {"account_id": account, "policy": policy.__dict__},
            )
        return policy
