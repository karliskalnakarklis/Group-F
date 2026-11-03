-- reporting: the sales ledger for head office and finance (docs/design.md, variant B, "Language").

-- copy: store list (source store administration), loaded from the seed at the first start
CREATE TABLE IF NOT EXISTS stores (
  store_id INT NOT NULL PRIMARY KEY
);
-- copies: ledger entries (source till), delivered by till's outbox
CREATE TABLE IF NOT EXISTS sale_entries (
  sale_id INT NOT NULL PRIMARY KEY,
  store_id INT NOT NULL,
  sold_on DATE NOT NULL,
  total DECIMAL(12,2) NOT NULL,
  tax DECIMAL(12,2) NOT NULL,
  KEY by_store (store_id, sold_on)
);
CREATE TABLE IF NOT EXISTS sale_entry_lines (
  sale_id INT NOT NULL,
  line_no INT NOT NULL,
  product_id INT NOT NULL,
  qty INT NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS sale_entry_vat (
  sale_id INT NOT NULL,
  rate DECIMAL(6,4) NOT NULL,
  net DECIMAL(12,2) NOT NULL,
  vat DECIMAL(12,2) NOT NULL,
  gross DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (sale_id, rate)
);
CREATE TABLE IF NOT EXISTS refund_entries (
  return_id INT NOT NULL PRIMARY KEY,
  sale_id INT NOT NULL,
  store_id INT NOT NULL,
  refunded_on DATE NOT NULL,
  refund_amount DECIMAL(12,2) NOT NULL,
  KEY by_store (store_id, refunded_on)
);
