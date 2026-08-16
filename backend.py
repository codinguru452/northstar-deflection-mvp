import os
import json
import hashlib
import secrets
import re
import threading
import time
from decimal import Decimal
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

import mysql.connector
from mysql.connector import Error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "northstar_db"),
}

SESSION_DAYS = 7

# Realistic logistics simulation: statuses advance by business-day milestones,
# not by a few minutes. This keeps the demo behaviour close to a real marketplace
# while remaining fully automatic.
TRACKING_MILESTONES = [
    ("Order Placed", 0),
    ("Payment Confirmed", 0),
    ("Processing", 1),
    ("Packed", 2),
    ("Handed to Courier", 3),
    ("In Transit", 4),
    ("Arrived at Local Hub", 5),
    ("Out for Delivery", 5),
    ("Delivered", 6),
]

TRACKING_NOTES = {
    "Order Placed": "Your order has been received.",
    "Payment Confirmed": "Your payment has been confirmed and the order is being prepared.",
    "Processing": "Your order is being prepared for dispatch.",
    "Packed": "Your order has been packed and is ready to leave the warehouse.",
    "Handed to Courier": "Your parcel has been handed to the delivery partner.",
    "In Transit": "Your parcel is in transit to the destination area.",
    "Arrived at Local Hub": "Your parcel has arrived at the local delivery hub.",
    "Out for Delivery": "Your parcel is with the delivery team and is out for delivery.",
    "Delivered": "Your order has been delivered.",
    "Cancelled": "This order has been cancelled.",
}

TRACKING_STATUSES = tuple(item[0] for item in TRACKING_MILESTONES)

def add_business_days(start, days):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

def tracking_due_status(created_at):
    # Returns the furthest status that should be reached by now.
    now = datetime.now()
    best = "Order Placed"
    for status, offset in TRACKING_MILESTONES:
        due = created_at if offset == 0 else add_business_days(created_at, offset)
        if now >= due:
            best = status
    return best

def advance_due_orders(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, order_number, status, created_at FROM orders WHERE status NOT IN ('Delivered','Cancelled')")
    orders = cur.fetchall()
    changed = 0
    for order in orders:
        target = tracking_due_status(order["created_at"])
        current = order["status"]
        if target not in TRACKING_STATUSES:
            continue
        try:
            current_index = TRACKING_STATUSES.index(current)
            target_index = TRACKING_STATUSES.index(target)
        except ValueError:
            continue
        if target_index <= current_index:
            continue
        for idx in range(current_index + 1, target_index + 1):
            next_status = TRACKING_STATUSES[idx]
            cur.execute("UPDATE orders SET status=%s WHERE id=%s", (next_status, order["id"]))
            cur.execute(
                "INSERT INTO order_status_history (order_id,status,notes) VALUES (%s,%s,%s)",
                (order["id"], next_status, TRACKING_NOTES[next_status]),
            )
            changed += 1
    if changed:
        conn.commit()
    cur.close()
    return changed

def tracking_worker():
    while True:
        conn = None
        try:
            conn = get_db()
            advance_due_orders(conn)
        except Exception as exc:
            print(f"Tracking worker warning: {exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        time.sleep(60)

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def password_verify(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, default=json_default).encode("utf-8")


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def send_json(self, status, data):
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def token(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return header[7:].strip()

    def current_customer(self, conn):
        raw_token = self.token()
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT c.id, c.full_name, c.email, c.phone, c.address
               FROM sessions s JOIN customers c ON c.id=s.customer_id
               WHERE s.token_hash=%s AND s.expires_at > NOW()""",
            (token_hash,),
        )
        customer = cur.fetchone()
        cur.close()
        return customer

    def current_admin(self, conn):
        raw_token = self.token()
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT a.id, a.username, a.full_name
               FROM admin_sessions s JOIN admin_users a ON a.id=s.admin_id
               WHERE s.token_hash=%s AND s.expires_at > NOW()""",
            (token_hash,),
        )
        admin = cur.fetchone()
        cur.close()
        return admin

    def require_admin(self, conn):
        admin = self.current_admin(conn)
        if not admin:
            self.send_json(401, {"error": "Admin login required."})
            return None
        return admin

    def require_customer(self, conn):
        customer = self.current_customer(conn)
        if not customer:
            self.send_json(401, {"error": "Please log in to continue."})
            return None
        return customer

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_get(parsed.path)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_post(parsed.path)
        else:
            self.send_error(404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_put(parsed.path)
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_delete(parsed.path)
        else:
            self.send_error(404)

    def api_get(self, path):
        try:
            conn = get_db()
            # Bring any due logistics milestones up to date before serving data.
            advance_due_orders(conn)
            if path == "/api/products":
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id,name,price,image,stock FROM products ORDER BY id")
                products = cur.fetchall()
                cur.close()
                conn.close()
                self.send_json(200, {"products": products})
                return

            if path == "/api/me":
                customer = self.current_customer(conn)
                conn.close()
                if not customer:
                    self.send_json(401, {"error": "Not logged in."})
                else:
                    self.send_json(200, {"customer": customer})
                return

            if path == "/api/cart":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT ci.product_id, ci.quantity, p.name, p.price, p.image,
                              (ci.quantity * p.price) AS line_total
                       FROM cart_items ci JOIN products p ON p.id=ci.product_id
                       WHERE ci.customer_id=%s ORDER BY ci.id""",
                    (customer["id"],),
                )
                items = cur.fetchall()
                cur.close()
                conn.close()
                self.send_json(200, {"items": items})
                return

            if path == "/api/admin/me":
                admin = self.current_admin(conn)
                conn.close()
                if not admin:
                    self.send_json(401, {"error": "Admin login required."})
                else:
                    self.send_json(200, {"admin": admin})
                return

            if path == "/api/admin/orders":
                admin = self.require_admin(conn)
                if not admin:
                    conn.close()
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT o.id, o.order_number, o.tracking_number, o.estimated_delivery_date,
                              o.total_amount, o.delivery_address, o.status,
                              o.created_at, o.updated_at, c.full_name, c.email, c.phone
                       FROM orders o JOIN customers c ON c.id=o.customer_id
                       ORDER BY o.created_at DESC"""
                )
                orders = cur.fetchall()
                cur.close(); conn.close()
                for order in orders:
                    order["total_amount"] = float(order["total_amount"])
                    order["created_at"] = order["created_at"].isoformat()
                    order["updated_at"] = order["updated_at"].isoformat()
                    if order.get("estimated_delivery_date"):
                        order["estimated_delivery_date"] = order["estimated_delivery_date"].isoformat()
                self.send_json(200, {"orders": orders})
                return

            if path == "/api/orders":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT id, order_number, tracking_number, estimated_delivery_date,
                              total_amount, delivery_address, status,
                              created_at, updated_at
                       FROM orders WHERE customer_id=%s ORDER BY created_at DESC""",
                    (customer["id"],),
                )
                orders = cur.fetchall()
                cur.close()
                conn.close()
                for order in orders:
                    order["total_amount"] = float(order["total_amount"])
                    order["created_at"] = order["created_at"].isoformat()
                    order["updated_at"] = order["updated_at"].isoformat()
                    if order.get("estimated_delivery_date"):
                        order["estimated_delivery_date"] = order["estimated_delivery_date"].isoformat()
                self.send_json(200, {"orders": orders})
                return

            if path.startswith("/api/orders/"):
                order_number = path.rsplit("/", 1)[-1]
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT id, order_number, tracking_number, estimated_delivery_date,
                              total_amount, delivery_address, status,
                              created_at, updated_at
                       FROM orders WHERE order_number=%s AND customer_id=%s""",
                    (order_number, customer["id"]),
                )
                order = cur.fetchone()
                if not order:
                    cur.close(); conn.close()
                    self.send_json(404, {"error": "Order not found."})
                    return
                cur.execute(
                    """SELECT product_name, price, quantity, (price*quantity) AS line_total
                       FROM order_items WHERE order_id=%s ORDER BY id""",
                    (order["id"],),
                )
                items = cur.fetchall()
                cur.execute(
                    """SELECT status, notes, created_at FROM order_status_history
                       WHERE order_id=%s ORDER BY created_at""",
                    (order["id"],),
                )
                history = cur.fetchall()
                cur.close(); conn.close()
                order["total_amount"] = float(order["total_amount"])
                order["created_at"] = order["created_at"].isoformat()
                order["updated_at"] = order["updated_at"].isoformat()
                if order.get("estimated_delivery_date"):
                    order["estimated_delivery_date"] = order["estimated_delivery_date"].isoformat()
                for item in items:
                    item["price"] = float(item["price"])
                    item["line_total"] = float(item["line_total"])
                for h in history:
                    h["created_at"] = h["created_at"].isoformat()
                self.send_json(200, {"order": order, "items": items, "history": history})
                return

            if path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message:
                    conn.close()
                    self.send_json(400, {"error": "Please enter a message."})
                    return

                customer = self.current_customer(conn)
                lower = message.lower()
                order_number = str(data.get("order_number", "")).strip().upper()
                match = re.search(r"\bNS[0-9A-Z]+\b", message.upper())
                if match:
                    order_number = match.group(0)

                # Order tracking through the chatbot.
                if order_number and any(word in lower for word in ("track", "where", "status", "order")):
                    if not customer:
                        conn.close()
                        self.send_json(200, {"reply": "Please sign in first so I can securely look up your order.", "action": "login"})
                        return
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT order_number,tracking_number,status,estimated_delivery_date,updated_at FROM orders WHERE order_number=%s AND customer_id=%s", (order_number, customer["id"]))
                    order = cur.fetchone()
                    cur.close(); conn.close()
                    if not order:
                        self.send_json(200, {"reply": f"I couldn't find order {order_number} on your account. Please check the order ID and try again."})
                        return
                    status_help = {
                        "Order Placed": "We have received your order.",
                        "Payment Confirmed": "Your payment has been confirmed.",
                        "Processing": "Your order is being prepared for dispatch.",
                        "Packed": "Your order has been packed and is ready to leave the warehouse.",
                        "Handed to Courier": "Your parcel has been handed to the delivery partner.",
                        "In Transit": "Your parcel is in transit to the destination area.",
                        "Arrived at Local Hub": "Your parcel has arrived at the local delivery hub.",
                        "Out for Delivery": "Your parcel is with the delivery team and is out for delivery.",
                        "Delivered": "Your order has been marked as delivered.",
                        "Cancelled": "This order has been cancelled.",
                    }
                    self.send_json(200, {
                        "reply": f"Order {order_number} is currently: {order['status']}. {status_help.get(order['status'], '')} Tracking number: {order.get('tracking_number') or 'not assigned yet'}. Estimated delivery: {order.get('estimated_delivery_date') or 'being calculated'}.",
                        "action": "track",
                        "order_number": order_number,
                    })
                    return

                # Show recent orders to a logged-in customer.
                if any(phrase in lower for phrase in ("my orders", "my order", "orders")) and customer:
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT order_number,status,total_amount FROM orders WHERE customer_id=%s ORDER BY created_at DESC LIMIT 5", (customer["id"],))
                    orders = cur.fetchall()
                    cur.close(); conn.close()
                    if orders:
                        lines = [f"{o['order_number']} — {o['status']} — KSh {float(o['total_amount']):,.0f}" for o in orders]
                        self.send_json(200, {"reply": "Here are your latest orders:\n" + "\n".join(lines), "action": "orders"})
                    else:
                        self.send_json(200, {"reply": "You don't have any orders yet. Visit the Shop and add some furniture to your cart."})
                    return

                # Cart information for a logged-in customer.
                if any(word in lower for word in ("cart", "basket")):
                    if not customer:
                        conn.close()
                        self.send_json(200, {"reply": "Please sign in to view your cart.", "action": "login"})
                        return
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT COALESCE(SUM(quantity),0) AS item_count, COALESCE(SUM(quantity*p.price),0) AS total FROM cart_items ci JOIN products p ON p.id=ci.product_id WHERE ci.customer_id=%s", (customer["id"],))
                    cart = cur.fetchone()
                    cur.close(); conn.close()
                    self.send_json(200, {"reply": f"Your cart has {int(cart['item_count'])} item(s) with a current subtotal of KSh {float(cart['total']):,.0f}.", "action": "cart"})
                    return

                # Product questions and simple recommendations.
                if any(word in lower for word in ("price", "product", "sofa", "chair", "furniture", "recommend", "available")):
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT name,price,stock FROM products ORDER BY id")
                    products = cur.fetchall()
                    cur.close(); conn.close()
                    wanted = "chair" if "chair" in lower else "sofa" if "sofa" in lower else None
                    selected = [p for p in products if wanted and wanted in p["name"].lower()] if wanted else products[:5]
                    lines = [f"{p['name']} — KSh {float(p['price']):,.0f} ({'in stock' if p['stock'] > 0 else 'out of stock'})" for p in selected[:5]]
                    self.send_json(200, {"reply": "Here are some options:\n" + "\n".join(lines) + "\n\nYou can open the Shop to add any item to your cart."})
                    return

                conn.close()
                if any(word in lower for word in ("hello", "hi", "hey")):
                    reply = "Hi! I'm the Northstar Assistant. I can help with products, your cart, orders, tracking, delivery, and returns."
                elif any(word in lower for word in ("delivery", "deliver", "shipping")):
                    reply = "Northstar delivery details are collected at checkout. Enter the address where you want your furniture delivered, then place your order."
                elif any(word in lower for word in ("return", "refund", "exchange")):
                    reply = "For returns or refunds, open Returns / Refunds, enter your order ID, choose a reason, and submit the request. Requests are reviewed before approval."
                elif any(word in lower for word in ("login", "sign in", "account")):
                    reply = "Use the account icon to sign in or create an account. After login, you'll be taken to the Shop."
                elif any(word in lower for word in ("checkout", "buy", "purchase", "place")):
                    reply = "Add your furniture to the cart, open Cart, then choose Checkout. Enter your delivery address and place the order. You'll then see it under My Orders."
                elif any(word in lower for word in ("contact", "support", "help")):
                    reply = "You can use the Contact Us page for Northstar support. I can also help you with products, cart, orders, tracking, delivery, and returns."
                else:
                    reply = "I can help with products and prices, your cart, checkout, My Orders, tracking an order ID, delivery, or returns/refunds. What would you like to know?"
                self.send_json(200, {"reply": reply})
                return

            if path == "/api/returns":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT r.id, r.order_id, o.order_number, r.reason, r.description,
                              r.status, r.created_at, r.updated_at
                       FROM return_requests r JOIN orders o ON o.id=r.order_id
                       WHERE r.customer_id=%s ORDER BY r.created_at DESC""",
                    (customer["id"],),
                )
                returns = cur.fetchall()
                cur.close(); conn.close()
                for item in returns:
                    item["created_at"] = item["created_at"].isoformat()
                    item["updated_at"] = item["updated_at"].isoformat()
                self.send_json(200, {"returns": returns})
                return

            self.send_json(404, {"error": "API endpoint not found."})
        except Error as exc:
            self.send_json(500, {"error": f"Database error: {exc}"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def api_post(self, path):
        try:
            data = self.read_json()
            conn = get_db()

            if path == "/api/admin/login":
                email = str(data.get("email", "")).strip().lower()
                password = str(data.get("password", ""))
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM admin_users WHERE email=%s", (email,))
                admin = cur.fetchone()
                if not admin or not password_verify(password, admin["password_hash"]):
                    cur.close(); conn.close()
                    self.send_json(401, {"error": "Invalid admin email or password."})
                    return
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                expires = datetime.now() + timedelta(days=SESSION_DAYS)
                cur.execute(
                    "INSERT INTO admin_sessions (admin_id,token_hash,expires_at) VALUES (%s,%s,%s)",
                    (admin["id"], token_hash, expires),
                )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(200, {"message": "Admin login successful.", "token": token, "admin": {"email": admin["email"], "full_name": admin["full_name"]}})
                return

            if path == "/api/admin/logout":
                raw_token = self.token()
                if raw_token:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM admin_sessions WHERE token_hash=%s", (hashlib.sha256(raw_token.encode()).hexdigest(),))
                    conn.commit(); cur.close()
                conn.close()
                self.send_json(200, {"message": "Admin logged out."})
                return

            if path == "/api/admin/orders/status":
                admin = self.require_admin(conn)
                if not admin:
                    conn.close()
                    return
                order_number = str(data.get("order_number", "")).strip().upper()
                status = str(data.get("status", "")).strip()
                notes = str(data.get("notes", "")).strip()
                valid_statuses = TRACKING_STATUSES + ("Cancelled",)
                if not order_number or status not in valid_statuses:
                    conn.close()
                    self.send_json(400, {"error": "Order ID and a valid order status are required."})
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id,status FROM orders WHERE order_number=%s", (order_number,))
                order = cur.fetchone()
                if not order:
                    cur.close(); conn.close()
                    self.send_json(404, {"error": "Order not found."})
                    return
                default_notes = TRACKING_NOTES
                if status != order["status"]:
                    cur.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order["id"]))
                    cur.execute(
                        "INSERT INTO order_status_history (order_id,status,notes) VALUES (%s,%s,%s)",
                        (order["id"], status, notes or default_notes[status]),
                    )
                elif notes:
                    cur.execute(
                        "INSERT INTO order_status_history (order_id,status,notes) VALUES (%s,%s,%s)",
                        (order["id"], status, notes),
                    )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(200, {"message": f"Order {order_number} updated to {status}."})
                return

            if path == "/api/register":
                full_name = str(data.get("full_name", "")).strip()
                email = str(data.get("email", "")).strip().lower()
                phone = str(data.get("phone", "")).strip()
                password = str(data.get("password", ""))
                if not full_name or not email or not phone or len(password) < 8:
                    conn.close()
                    self.send_json(400, {"error": "Please provide all required details. Password must be at least 8 characters."})
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id FROM customers WHERE email=%s", (email,))
                if cur.fetchone():
                    cur.close(); conn.close()
                    self.send_json(409, {"error": "An account with this email already exists."})
                    return
                cur.execute(
                    """INSERT INTO customers (full_name,email,phone,password_hash)
                       VALUES (%s,%s,%s,%s)""",
                    (full_name, email, phone, password_hash(password)),
                )
                customer_id = cur.lastrowid
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                expires = datetime.now() + timedelta(days=SESSION_DAYS)
                cur.execute(
                    """INSERT INTO sessions (customer_id,token_hash,expires_at)
                       VALUES (%s,%s,%s)""",
                    (customer_id, token_hash, expires),
                )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(201, {"message": "Account created.", "token": token})
                return

            if path == "/api/login":
                email = str(data.get("email", "")).strip().lower()
                password = str(data.get("password", ""))
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT * FROM customers WHERE email=%s", (email,))
                customer = cur.fetchone()
                if not customer or not password_verify(password, customer["password_hash"]):
                    cur.close(); conn.close()
                    self.send_json(401, {"error": "Invalid email or password."})
                    return
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                expires = datetime.now() + timedelta(days=SESSION_DAYS)
                cur.execute(
                    "INSERT INTO sessions (customer_id,token_hash,expires_at) VALUES (%s,%s,%s)",
                    (customer["id"], token_hash, expires),
                )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(200, {"message": "Login successful.", "token": token})
                return

            if path == "/api/logout":
                raw_token = self.token()
                if raw_token:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM sessions WHERE token_hash=%s", (hashlib.sha256(raw_token.encode()).hexdigest(),))
                    conn.commit()
                    cur.close()
                conn.close()
                self.send_json(200, {"message": "Logged out."})
                return

            if path == "/api/cart":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                product_id = int(data.get("product_id", 0))
                quantity = int(data.get("quantity", 1))
                if quantity < 1:
                    quantity = 1
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id,stock FROM products WHERE id=%s", (product_id,))
                product = cur.fetchone()
                if not product:
                    cur.close(); conn.close()
                    self.send_json(404, {"error": "Product not found."})
                    return
                cur.execute("SELECT quantity FROM cart_items WHERE customer_id=%s AND product_id=%s", (customer["id"], product_id))
                existing = cur.fetchone()
                new_qty = (existing["quantity"] if existing else 0) + quantity
                if new_qty > product["stock"]:
                    cur.close(); conn.close()
                    self.send_json(400, {"error": "That quantity is not currently available."})
                    return
                cur.execute(
                    """INSERT INTO cart_items (customer_id,product_id,quantity)
                       VALUES (%s,%s,%s)
                       ON DUPLICATE KEY UPDATE quantity=VALUES(quantity)""",
                    (customer["id"], product_id, new_qty),
                )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(200, {"message": "Added to cart.", "quantity": new_qty})
                return

            if path == "/api/orders":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                address = str(data.get("delivery_address", "")).strip()
                if not address:
                    conn.close()
                    self.send_json(400, {"error": "Delivery address is required."})
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT ci.product_id, ci.quantity, p.name, p.price, p.stock
                       FROM cart_items ci JOIN products p ON p.id=ci.product_id
                       WHERE ci.customer_id=%s""",
                    (customer["id"],),
                )
                items = cur.fetchall()
                if not items:
                    cur.close(); conn.close()
                    self.send_json(400, {"error": "Your cart is empty."})
                    return
                total = 0
                for item in items:
                    if item["quantity"] > item["stock"]:
                        cur.close(); conn.close()
                        self.send_json(400, {"error": f"Not enough stock for {item['name']}."})
                        return
                    total += float(item["price"]) * item["quantity"]
                order_number = "NS" + datetime.now().strftime("%y%m%d%H%M%S") + secrets.token_hex(2).upper()
                tracking_number = "NST-KE-" + secrets.token_hex(4).upper()
                estimated_delivery_date = add_business_days(datetime.now(), 6).date()
                cur.execute(
                    """INSERT INTO orders
                       (order_number,tracking_number,estimated_delivery_date,customer_id,total_amount,delivery_address,status)
                       VALUES (%s,%s,%s,%s,%s,%s,'Order Placed')""",
                    (
                        order_number,
                        tracking_number,
                        estimated_delivery_date,
                        customer["id"], total, address,
                    ),
                )
                order_id = cur.lastrowid
                for item in items:
                    cur.execute(
                        """INSERT INTO order_items
                           (order_id,product_id,product_name,price,quantity)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (order_id, item["product_id"], item["name"], item["price"], item["quantity"]),
                    )
                    cur.execute("UPDATE products SET stock=stock-%s WHERE id=%s", (item["quantity"], item["product_id"]))
                cur.execute(
                    """INSERT INTO order_status_history (order_id,status,notes)
                       VALUES (%s,'Order Placed','Your order has been received.')""",
                    (order_id,),
                )
                cur.execute("DELETE FROM cart_items WHERE customer_id=%s", (customer["id"],))
                conn.commit()
                cur.close(); conn.close()
                self.send_json(201, {
                    "message": "Order placed.",
                    "order_number": order_number,
                    "tracking_number": tracking_number,
                    "estimated_delivery_date": estimated_delivery_date.isoformat(),
                })
                return

            if path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message:
                    conn.close()
                    self.send_json(400, {"error": "Please enter a message."})
                    return

                customer = self.current_customer(conn)
                lower = message.lower()
                order_number = str(data.get("order_number", "")).strip().upper()
                match = re.search(r"\bNS[0-9A-Z]+\b", message.upper())
                if match:
                    order_number = match.group(0)

                # Order tracking through the chatbot.
                if order_number and any(word in lower for word in ("track", "where", "status", "order")):
                    if not customer:
                        conn.close()
                        self.send_json(200, {"reply": "Please sign in first so I can securely look up your order.", "action": "login"})
                        return
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT order_number,tracking_number,status,estimated_delivery_date,updated_at FROM orders WHERE order_number=%s AND customer_id=%s", (order_number, customer["id"]))
                    order = cur.fetchone()
                    cur.close(); conn.close()
                    if not order:
                        self.send_json(200, {"reply": f"I couldn't find order {order_number} on your account. Please check the order ID and try again."})
                        return
                    status_help = {
                        "Order Placed": "We have received your order.",
                        "Payment Confirmed": "Your payment has been confirmed.",
                        "Processing": "Your order is being prepared for dispatch.",
                        "Packed": "Your order has been packed and is ready to leave the warehouse.",
                        "Handed to Courier": "Your parcel has been handed to the delivery partner.",
                        "In Transit": "Your parcel is in transit to the destination area.",
                        "Arrived at Local Hub": "Your parcel has arrived at the local delivery hub.",
                        "Out for Delivery": "Your parcel is with the delivery team and is out for delivery.",
                        "Delivered": "Your order has been marked as delivered.",
                        "Cancelled": "This order has been cancelled.",
                    }
                    self.send_json(200, {
                        "reply": f"Order {order_number} is currently: {order['status']}. {status_help.get(order['status'], '')} Tracking number: {order.get('tracking_number') or 'not assigned yet'}. Estimated delivery: {order.get('estimated_delivery_date') or 'being calculated'}.",
                        "action": "track",
                        "order_number": order_number,
                    })
                    return

                # Show recent orders to a logged-in customer.
                if any(phrase in lower for phrase in ("my orders", "my order", "orders")) and customer:
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT order_number,status,total_amount FROM orders WHERE customer_id=%s ORDER BY created_at DESC LIMIT 5", (customer["id"],))
                    orders = cur.fetchall()
                    cur.close(); conn.close()
                    if orders:
                        lines = [f"{o['order_number']} — {o['status']} — KSh {float(o['total_amount']):,.0f}" for o in orders]
                        self.send_json(200, {"reply": "Here are your latest orders:\n" + "\n".join(lines), "action": "orders"})
                    else:
                        self.send_json(200, {"reply": "You don't have any orders yet. Visit the Shop and add some furniture to your cart."})
                    return

                # Cart information for a logged-in customer.
                if any(word in lower for word in ("cart", "basket")):
                    if not customer:
                        conn.close()
                        self.send_json(200, {"reply": "Please sign in to view your cart.", "action": "login"})
                        return
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT COALESCE(SUM(quantity),0) AS item_count, COALESCE(SUM(quantity*p.price),0) AS total FROM cart_items ci JOIN products p ON p.id=ci.product_id WHERE ci.customer_id=%s", (customer["id"],))
                    cart = cur.fetchone()
                    cur.close(); conn.close()
                    self.send_json(200, {"reply": f"Your cart has {int(cart['item_count'])} item(s) with a current subtotal of KSh {float(cart['total']):,.0f}.", "action": "cart"})
                    return

                # Product questions and simple recommendations.
                if any(word in lower for word in ("price", "product", "sofa", "chair", "furniture", "recommend", "available")):
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT name,price,stock FROM products ORDER BY id")
                    products = cur.fetchall()
                    cur.close(); conn.close()
                    wanted = "chair" if "chair" in lower else "sofa" if "sofa" in lower else None
                    selected = [p for p in products if wanted and wanted in p["name"].lower()] if wanted else products[:5]
                    lines = [f"{p['name']} — KSh {float(p['price']):,.0f} ({'in stock' if p['stock'] > 0 else 'out of stock'})" for p in selected[:5]]
                    self.send_json(200, {"reply": "Here are some options:\n" + "\n".join(lines) + "\n\nYou can open the Shop to add any item to your cart."})
                    return

                conn.close()
                if any(word in lower for word in ("hello", "hi", "hey")):
                    reply = "Hi! I'm the Northstar Assistant. I can help with products, your cart, orders, tracking, delivery, and returns."
                elif any(word in lower for word in ("delivery", "deliver", "shipping")):
                    reply = "Northstar delivery details are collected at checkout. Enter the address where you want your furniture delivered, then place your order."
                elif any(word in lower for word in ("return", "refund", "exchange")):
                    reply = "For returns or refunds, open Returns / Refunds, enter your order ID, choose a reason, and submit the request. Requests are reviewed before approval."
                elif any(word in lower for word in ("login", "sign in", "account")):
                    reply = "Use the account icon to sign in or create an account. After login, you'll be taken to the Shop."
                elif any(word in lower for word in ("checkout", "buy", "purchase", "place")):
                    reply = "Add your furniture to the cart, open Cart, then choose Checkout. Enter your delivery address and place the order. You'll then see it under My Orders."
                elif any(word in lower for word in ("contact", "support", "help")):
                    reply = "You can use the Contact Us page for Northstar support. I can also help you with products, cart, orders, tracking, delivery, and returns."
                else:
                    reply = "I can help with products and prices, your cart, checkout, My Orders, tracking an order ID, delivery, or returns/refunds. What would you like to know?"
                self.send_json(200, {"reply": reply})
                return

            if path == "/api/returns":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close()
                    return
                order_number = str(data.get("order_number", "")).strip()
                reason = str(data.get("reason", "")).strip()
                description = str(data.get("description", "")).strip()
                if not order_number or not reason:
                    conn.close()
                    self.send_json(400, {"error": "Order number and return reason are required."})
                    return
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """SELECT id,status FROM orders WHERE order_number=%s AND customer_id=%s""",
                    (order_number, customer["id"]),
                )
                order = cur.fetchone()
                if not order:
                    cur.close(); conn.close()
                    self.send_json(404, {"error": "Order not found."})
                    return
                if order["status"] not in ("Delivered", "Out for Delivery"):
                    cur.close(); conn.close()
                    self.send_json(400, {"error": "A return/refund request can be submitted after delivery."})
                    return
                cur.execute(
                    "SELECT id FROM return_requests WHERE order_id=%s AND customer_id=%s AND status NOT IN ('Rejected','Refund Processed')",
                    (order["id"], customer["id"]),
                )
                if cur.fetchone():
                    cur.close(); conn.close()
                    self.send_json(409, {"error": "A return/refund request already exists for this order."})
                    return
                cur.execute(
                    """INSERT INTO return_requests (order_id,customer_id,reason,description)
                       VALUES (%s,%s,%s,%s)""",
                    (order["id"], customer["id"], reason, description),
                )
                conn.commit()
                cur.close(); conn.close()
                self.send_json(201, {"message": "Return/refund request submitted."})
                return

            self.send_json(404, {"error": "API endpoint not found."})
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid request data."})
        except Error as exc:
            self.send_json(500, {"error": f"Database error: {exc}"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def api_put(self, path):
        try:
            data = self.read_json()
            conn = get_db()
            if path == "/api/cart":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close(); return
                product_id = int(data.get("product_id", 0))
                quantity = int(data.get("quantity", 0))
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT stock FROM products WHERE id=%s", (product_id,))
                product = cur.fetchone()
                if not product:
                    cur.close(); conn.close()
                    self.send_json(404, {"error": "Product not found."}); return
                if quantity <= 0:
                    cur.execute("DELETE FROM cart_items WHERE customer_id=%s AND product_id=%s", (customer["id"], product_id))
                elif quantity > product["stock"]:
                    cur.close(); conn.close()
                    self.send_json(400, {"error": "That quantity is not currently available."}); return
                else:
                    cur.execute(
                        """UPDATE cart_items SET quantity=%s
                           WHERE customer_id=%s AND product_id=%s""",
                        (quantity, customer["id"], product_id),
                    )
                conn.commit(); cur.close(); conn.close()
                self.send_json(200, {"message": "Cart updated."}); return
            self.send_json(404, {"error": "API endpoint not found."})
        except Error as exc:
            self.send_json(500, {"error": f"Database error: {exc}"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def api_delete(self, path):
        try:
            conn = get_db()
            if path == "/api/cart":
                customer = self.require_customer(conn)
                if not customer:
                    conn.close(); return
                data = self.read_json()
                product_id = int(data.get("product_id", 0))
                cur = conn.cursor()
                cur.execute("DELETE FROM cart_items WHERE customer_id=%s AND product_id=%s", (customer["id"], product_id))
                conn.commit(); cur.close(); conn.close()
                self.send_json(200, {"message": "Item removed."}); return
            self.send_json(404, {"error": "API endpoint not found."})
        except Error as exc:
            self.send_json(500, {"error": f"Database error: {exc}"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", 8000), APIHandler)
    print("Northstar is running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server.")
    threading.Thread(target=tracking_worker, daemon=True).start()
    server.serve_forever()
