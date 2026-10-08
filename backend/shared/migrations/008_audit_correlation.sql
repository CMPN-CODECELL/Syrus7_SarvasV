ALTER TABLE algoshield.audit ADD COLUMN correlation_id TEXT;
CREATE INDEX audit_correlation ON algoshield.audit(correlation_id, sequence);
