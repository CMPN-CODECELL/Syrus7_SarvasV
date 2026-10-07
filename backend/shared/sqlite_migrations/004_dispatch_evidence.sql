ALTER TABLE orders ADD COLUMN dispatch_started INTEGER NOT NULL DEFAULT 1 CHECK (dispatch_started IN (0,1));
