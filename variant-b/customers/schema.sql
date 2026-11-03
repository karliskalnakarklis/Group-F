-- customers: customers and loyalty. Own model, business names (docs/design.md, variant B, "Language").
-- The only store of variant B with personal data. No legacy password, no US state.

CREATE TABLE IF NOT EXISTS customers (
  customer_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(50) NOT NULL,
  last_name VARCHAR(50) NOT NULL,
  email VARCHAR(50) NOT NULL,
  phone VARCHAR(30) NOT NULL,
  street VARCHAR(50) NOT NULL,
  zip_code VARCHAR(10) NOT NULL,
  city VARCHAR(50) NOT NULL,
  reward_points INT NOT NULL DEFAULT 0
);
-- CR2: what the 12-month spend is computed from (earn: sale date and total, refund: sale date and amount)
CREATE TABLE IF NOT EXISTS point_movements (
  movement_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  customer_id INT NOT NULL,
  kind ENUM('earn', 'refund') NOT NULL,
  sale_date DATE NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  KEY by_customer (customer_id, sale_date)
);
