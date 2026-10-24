PRAGMA foreign_keys = ON;

-- Research database (schema v2): A-shares (SH/SZ/BJ) and Hong Kong stocks (HK).
-- Prices in `bars` are RAW (as traded). adj_factor is the forward-adjust factor:
--   forward-adjusted price = raw price * adj_factor   (adj_factor = 1 on the latest bar)
-- 港股通 (hk_connect) is a trading channel, not a listing venue: HK stocks are stored once with
-- market = 'hk_stock' and strategies choose market = 'hk_connect' to trade them from a CNY account.

CREATE TABLE IF NOT EXISTS schema_info (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('a_share', 'hk_stock')),
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ', 'HK')),
  asset_type TEXT NOT NULL DEFAULT 'stock',
  currency TEXT NOT NULL DEFAULT 'CNY',
  lot_size INTEGER,
  connect_eligible INTEGER,
  listed_date TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bars (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  frequency TEXT NOT NULL CHECK (frequency IN ('1d', '60m', '30m', '15m')),
  trade_time TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  amount REAL NOT NULL,
  adj_factor REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (symbol, frequency, trade_time),
  FOREIGN KEY (symbol) REFERENCES instruments(symbol)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  ex_date TEXT NOT NULL,
  cash_dividend REAL NOT NULL DEFAULT 0,   -- per share, quote currency
  bonus_ratio REAL NOT NULL DEFAULT 0,     -- new shares per share (10送5 = 0.5)
  currency TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  UNIQUE (symbol, ex_date, source),
  FOREIGN KEY (symbol) REFERENCES instruments(symbol)
);

CREATE TABLE IF NOT EXISTS fx_rates (
  pair TEXT NOT NULL,                      -- e.g. HKDCNY = CNY per 1 HKD
  rate_date TEXT NOT NULL,
  rate REAL NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  PRIMARY KEY (pair, rate_date)
);

CREATE TABLE IF NOT EXISTS data_loads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  symbol TEXT NOT NULL,
  frequency TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  row_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_bars_symbol_frequency_time
ON bars(symbol, frequency, trade_time);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_symbol_date
ON corporate_actions(symbol, ex_date);

CREATE INDEX IF NOT EXISTS idx_data_loads_symbol_frequency
ON data_loads(symbol, frequency, started_at);

INSERT OR REPLACE INTO schema_info(key, value) VALUES ('schema_version', '2');
