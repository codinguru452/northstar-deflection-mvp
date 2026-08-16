# Northstar MVP - MySQL + Python

This version keeps the existing Northstar HTML/CSS/Bootstrap/Vanilla JavaScript design and adds a small Python backend.

## Stack

- HTML5
- CSS3 + existing Bootstrap
- Vanilla JavaScript
- Python 3.10+
- MySQL 8
- `mysql-connector-python`
- Python standard-library HTTP server (no Flask, Django, FastAPI, Node.js, or Express)

## Added functionality

- Working Add to Cart button
- Customer registration
- Customer login/logout
- Customer details stored in MySQL
- Customer-specific cart
- Cart quantity controls and remove
- Checkout and order creation
- My Orders
- Track My Order
- Order status history
- Return / Refund request
- Return / Refund request status
- Customer-facing Northstar Assistant chatbot
- Admin order management dashboard for realistic tracking updates
- Add-to-cart hover tooltip and success notification
- Chatbot can answer product, cart, delivery, order, tracking and returns questions

## 1. Install MySQL

Use MySQL 8 directly. XAMPP and phpMyAdmin are not required.

## 2. Create the database

Open the MySQL terminal and run/import:

    schema.sql

This creates/uses `northstar_db`, the required tables, sessions, cart, orders, returns, and the eight existing shop products.

## 3. Install the Python MySQL driver

Open a terminal in this project folder:

    python -m pip install -r requirements.txt

## 4. Configure MySQL if needed

By default the backend expects:

    Host: 127.0.0.1
    Port: 3306
    User: root
    Password: empty
    Database: northstar_db

If your MySQL installation has a password, set it before starting the server.

Windows Command Prompt example:

    set MYSQL_PASSWORD=your_mysql_password

PowerShell:

    $env:MYSQL_PASSWORD="your_mysql_password"

Other optional settings:

    MYSQL_HOST
    MYSQL_PORT
    MYSQL_USER
    MYSQL_DATABASE

## 5. Start Northstar

Run:

    python backend.py

If your MySQL root account has a password, set it in the same Git Bash terminal first:

    export MYSQL_PASSWORD='your_mysql_password'

Then open:

    http://127.0.0.1:8000

Do NOT open the HTML files by double-clicking them. The Python server must be running because the pages call `/api/...` endpoints.

## 6. Customer flow

1. Create an account or sign in.
2. After login, the customer is taken to Shop.
3. Click the + button on a product to add it to the customer-specific cart.
4. Open Cart and change quantities or remove items.
5. Choose Checkout and enter the delivery address.
6. Place the order; the customer is taken to My Orders.
7. Use Track Order and enter the order ID to see the current status.
8. Use Returns / Refunds to submit and view return/refund requests.

## Order tracking

A newly placed order starts at:

Order Placed

The database supports:

- Order Placed
- Payment Confirmed
- Processing
- Packed
- Out for Delivery
- Delivered
- Cancelled

The customer sees the current status and status history.

## Admin order tracking

The project now includes `admin.html`. The administrator can sign in, view customer orders, choose a new order status, and add a tracking note. Every status change is saved in `order_status_history`, so the customer tracking page shows a realistic timeline.

Open:

    http://127.0.0.1:8000/admin.html

Default local administrator:

    Username: admin
    Password: NorthstarAdmin@2026

For an existing `northstar_db` database, run `admin_setup.sql` once. If you are creating the database from scratch, the updated `schema.sql` already creates the admin tables and account.

## Important

The Vercel deployment currently serves the frontend. This Python/MySQL version is designed to run locally with the included backend. A production deployment needs the Python API and MySQL database hosted on services that support them; the static Vercel frontend alone cannot execute `backend.py`.

## Files added

- `admin.html` - administrator login and order tracking dashboard
- `js/admin.js` - admin login and order status management
- `admin_setup.sql` - one-time admin tables/setup for an existing database

- `backend.py` - Python API and static-file server
- `schema.sql` - MySQL database and tables
- `requirements.txt` - Python dependency
- `js/app.js` - cart, authentication, checkout, orders, tracking and returns
- `account.html` - customer account and My Orders
- `track-order.html` - order tracking
- `return-refund.html` - return/refund requests


## Updating order status during testing
The customer tracking page reads the order status from MySQL. A newly placed order starts at `Order Placed`. For local testing, an administrator can move an order forward directly in MySQL, for example:

    UPDATE orders SET status='Processing' WHERE order_number='YOUR_ORDER_ID';
    INSERT INTO order_status_history (order_id,status,notes)
    SELECT id,'Processing','Your order is being prepared.' FROM orders WHERE order_number='YOUR_ORDER_ID';

Use the same pattern for `Packed`, `Out for Delivery`, and `Delivered`.

## Chatbot
The included chatbot is a lightweight local Northstar Assistant. It does not require an external AI API key. It can answer common customer questions and, when a logged-in customer provides an order ID, it can look up that customer's order status securely.
