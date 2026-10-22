-- Legacy schema of the PoS monolith (HS24 dump), with the extensions the
-- monolith added over the years (marked "added"). Float money columns and
-- odd types (phone numbers as double) are legacy and stay.

CREATE TABLE IF NOT EXISTS customer_info (
  customer_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email varchar(50) NOT NULL, password varchar(60) NOT NULL,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL,
  phone_number double NOT NULL, rewards float DEFAULT NULL,
  street_address varchar(50) NOT NULL, city varchar(50) NOT NULL,
  state varchar(2) NOT NULL, zip_code int NOT NULL
);
CREATE TABLE IF NOT EXISTS employee_info (
  employee_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email varchar(50) NOT NULL, password varchar(50) NOT NULL, pin_number int NOT NULL,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL, user_id double NOT NULL,
  phone_number double NOT NULL, SSN double NOT NULL, street_address varchar(50) NOT NULL,
  city varchar(50) NOT NULL, state varchar(2) NOT NULL, zip_code int NOT NULL,
  start_date date NOT NULL, company_name varchar(50) NOT NULL, number_of_stores varchar(11) DEFAULT NULL,
  user_type int NOT NULL, customer_id int DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS stores (
  SID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name varchar(50) NOT NULL, employee_id int NOT NULL
);
-- added: which register stands in which store
CREATE TABLE IF NOT EXISTS store_registers (
  register_num int NOT NULL PRIMARY KEY, SID int NOT NULL
);
CREATE TABLE IF NOT EXISTS vendorinfo (
  vendor_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name varchar(50) NOT NULL, department varchar(100) NOT NULL,
  street_address varchar(50) NOT NULL, city varchar(50) NOT NULL, state varchar(2) NOT NULL,
  zip_code int NOT NULL, phone_number double NOT NULL, fax_number double NOT NULL, email varchar(50) NOT NULL
);
CREATE TABLE IF NOT EXISTS product_inventory (
  product_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  brand varchar(50) NOT NULL, description varchar(50) NOT NULL, productName varchar(50) NOT NULL,
  productType varchar(50) NOT NULL, productSubType varchar(50) NOT NULL,
  unit_price float NOT NULL, cost float NOT NULL, in_stock int NOT NULL, vendor_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS gift_card (
  gift_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  promo_number double NOT NULL, card_balance float NOT NULL,
  ticket_id int DEFAULT NULL, customer_id int DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS tax_table (
  TTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tax_year year NOT NULL, state_tax float NOT NULL, county_tax float NOT NULL,
  city_rate float NOT NULL, tax_rate float NOT NULL
);
-- one row per register session
CREATE TABLE IF NOT EXISTS registers_table (
  register_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  open_total float NOT NULL, close_total float DEFAULT NULL, register_num int NOT NULL,
  open_emp_id int NOT NULL, close_emp_id int DEFAULT NULL,
  open_time datetime NOT NULL, close_time datetime DEFAULT NULL,
  drop_time datetime DEFAULT NULL, drop_emp_id int DEFAULT NULL, drop_total float DEFAULT NULL,
  note varchar(100) DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS ticket_system (
  ticket_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  date date NOT NULL, company_name varchar(50) DEFAULT NULL, time time NOT NULL,
  quantity int NOT NULL, subtotal float NOT NULL, total float NOT NULL, cost float NOT NULL,
  discount float DEFAULT NULL, tax float NOT NULL, tax_rate float NOT NULL,
  cash float NOT NULL, credit float NOT NULL, cart_purchase tinyint(1) NOT NULL,
  customer_id int DEFAULT NULL, employee_id int NOT NULL,
  register_id int NOT NULL,          -- added: the register session
  reward_points int NOT NULL DEFAULT 0  -- added
);
CREATE TABLE IF NOT EXISTS cart_inprogress (
  CID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  customer_id int DEFAULT NULL, ticket_id int DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS item_list (
  ITID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  CID int NOT NULL, qty int NOT NULL, product_id int NOT NULL,
  unit_price float NOT NULL  -- added: price at the time of the sale
);
-- added: gift card payments (cash and credit are columns of ticket_system)
CREATE TABLE IF NOT EXISTS ticket_gift_payment (
  ticket_id int NOT NULL, gift_id int NOT NULL, amount float NOT NULL
);
CREATE TABLE IF NOT EXISTS return_table (
  RTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  ticket_id int NOT NULL, date date NOT NULL, time time NOT NULL,
  refunds float NOT NULL, exchanges float NOT NULL,
  register_id int NOT NULL  -- added: the register session
);
-- added: returned lines
CREATE TABLE IF NOT EXISTS return_items (
  RTID int NOT NULL, product_id int NOT NULL, qty int NOT NULL
);
CREATE TABLE IF NOT EXISTS orders_ticket (
  OTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  date date NOT NULL, time time NOT NULL, quantity int NOT NULL,
  subtotal float NOT NULL, total float NOT NULL, discount float DEFAULT NULL,
  tax float DEFAULT NULL, tax_rate float DEFAULT NULL, cash float DEFAULT NULL, credit float DEFAULT NULL,
  status int NOT NULL, employee_id int NOT NULL, vendor_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  OID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  OTID int NOT NULL, stock_amount int NOT NULL, product_id int NOT NULL
);
