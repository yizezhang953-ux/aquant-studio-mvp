PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market = 'a_share'),
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ')),
  asset_type TEXT NOT NULL DEFAULT 'stock',
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

CREATE TABLE IF NOT EXISTS data_loads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  symbol TEXT NOT NULL,
  frequency TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  row_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  error_message TEXT,
  FOREIGN KEY (symbol) REFERENCES instruments(symbol)
);

CREATE INDEX IF NOT EXISTS idx_bars_symbol_frequency_time
ON bars(symbol, frequency, trade_time);

CREATE INDEX IF NOT EXISTS idx_data_loads_symbol_frequency
ON data_loads(symbol, frequency, started_at);
