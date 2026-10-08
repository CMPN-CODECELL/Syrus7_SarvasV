ALTER TABLE audit ADD COLUMN correlation_id TEXT;
CREATE INDEX audit_correlation ON audit(correlation_id, sequence);
