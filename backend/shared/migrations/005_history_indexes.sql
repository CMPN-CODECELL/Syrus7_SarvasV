CREATE INDEX orders_history ON algoshield.orders(created DESC,id DESC);
CREATE INDEX fills_history ON algoshield.fills(timestamp DESC,id DESC);
CREATE INDEX audit_events ON algoshield.audit(type,sequence);
