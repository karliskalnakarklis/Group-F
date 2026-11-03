-- purchasing: assortment and purchasing. Own model, business names (docs/design.md, variant B, "Language").

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name VARCHAR(50) NOT NULL,
  department VARCHAR(100) NOT NULL,
  street VARCHAR(50) NOT NULL,
  zip_code VARCHAR(10) NOT NULL,
  city VARCHAR(50) NOT NULL,
  phone VARCHAR(30) NOT NULL,
  fax VARCHAR(30) NOT NULL,
  email VARCHAR(50) NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
  product_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  brand VARCHAR(50) NOT NULL,
  description VARCHAR(50) NOT NULL,
  category VARCHAR(50) NOT NULL,
  subcategory VARCHAR(50) NOT NULL,
  retail_price DECIMAL(12,2) NOT NULL,
  cost DECIMAL(12,2) NOT NULL,
  supplier_id INT NOT NULL
);
-- copy: staff IDs (source HR), loaded from the seed at the first start
CREATE TABLE IF NOT EXISTS staff (
  staff_id INT NOT NULL PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  purchase_order_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  supplier_id INT NOT NULL,
  ordered_by INT NOT NULL,
  ordered_at DATETIME NOT NULL,
  total_cost DECIMAL(12,2) NOT NULL,
  status ENUM('open', 'received') NOT NULL,
  received_by INT NULL,
  received_at DATETIME NULL
);
CREATE TABLE IF NOT EXISTS order_lines (
  purchase_order_id INT NOT NULL,
  line_no INT NOT NULL,
  product_id INT NOT NULL,
  qty INT NOT NULL,
  PRIMARY KEY (purchase_order_id, line_no)
);
