CREATE TABLE account_risk_policies (
    account TEXT PRIMARY KEY REFERENCES accounts(id),
    max_net_position_per_symbol INTEGER CHECK (max_net_position_per_symbol IS NULL OR max_net_position_per_symbol > 0),
    max_gross_virtual_position_per_symbol INTEGER CHECK (max_gross_virtual_position_per_symbol IS NULL OR max_gross_virtual_position_per_symbol > 0));
