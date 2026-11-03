-- till: selling at the till. Own model, business names (docs/design.md, variant B, "Language").

-- copies, loaded from the seed at the first start
CREATE TABLE IF NOT EXISTS registers (
  register_no INT NOT NULL PRIMARY KEY,
  store_id INT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
  staff_id INT NOT NULL PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS price_list (
  product_id INT NOT NULL PRIMARY KEY,
  unit_price DECIMAL(12,2) NOT NULL,
  category VARCHAR(50) NOT NULL
);

-- own data
CREATE TABLE IF NOT EXISTS stock (
  product_id INT NOT NULL PRIMARY KEY,
  on_hand INT NOT NULL
);
CREATE TABLE IF NOT EXISTS gift_cards (
  gift_card_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  balance DECIMAL(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS shifts (
  shift_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  register_no INT NOT NULL,
  opened_by INT NOT NULL,
  opened_at DATETIME NOT NULL,
  opening_cash DECIMAL(12,2) NOT NULL,
  closed_by INT NULL,
  closed_at DATETIME NULL,
  counted_cash DECIMAL(12,2) NULL,
  KEY open_shift (register_no, closed_at)
);
CREATE TABLE IF NOT EXISTS sales (
  sale_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  shift_id INT NOT NULL,
  register_no INT NOT NULL,
  store_id INT NOT NULL,
  sold_on DATE NOT NULL,
  sold_at DATETIME NOT NULL,
  staff_id INT NOT NULL,
  customer_id INT NULL,
  subtotal DECIMAL(12,2) NOT NULL,
  tax DECIMAL(12,2) NOT NULL,
  total DECIMAL(12,2) NOT NULL,
  reward_points_earned INT NOT NULL,
  tier VARCHAR(10) NULL,
  points_per_chf INT NULL,
  KEY by_shift (shift_id)
);
CREATE TABLE IF NOT EXISTS sale_vat (
  sale_id INT NOT NULL,
  rate DECIMAL(6,4) NOT NULL,
  net DECIMAL(12,2) NOT NULL,
  vat DECIMAL(12,2) NOT NULL,
  gross DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (sale_id, rate)
);
CREATE TABLE IF NOT EXISTS sale_lines (
  sale_id INT NOT NULL,
  line_no INT NOT NULL,
  product_id INT NOT NULL,
  qty INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS payments (
  sale_id INT NOT NULL,
  line_no INT NOT NULL,
  tender ENUM('cash', 'card', 'gift_card') NOT NULL,
  gift_card_id INT NULL,
  amount DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS returns (
  return_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sale_id INT NOT NULL,
  shift_id INT NOT NULL,
  register_no INT NOT NULL,
  store_id INT NOT NULL,
  returned_on DATE NOT NULL,
  returned_at DATETIME NOT NULL,
  staff_id INT NOT NULL,
  refund_amount DECIMAL(12,2) NOT NULL,
  KEY by_sale (sale_id),
  KEY by_shift (shift_id)
);
CREATE TABLE IF NOT EXISTS return_lines (
  return_id INT NOT NULL,
  product_id INT NOT NULL,
  qty INT NOT NULL,
  PRIMARY KEY (return_id, product_id)
);
