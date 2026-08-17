Northstar MVP 

Stack

- HTML5
- CSS3 + existing Bootstrap
- Vanilla JavaScript
- Python 3.10+
- MySQL 8
- Python standard-library HTTP server (no Flask, Django, FastAPI, Node.js, or Express)

key functionality

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


Customer flow

1. Create an account or sign in.
2. After login, the customer is taken to Shop.
3. Click the + button on a product to add it to the customer-specific cart.
4. Open Cart and change quantities or remove items.
5. Choose Checkout and enter the delivery address.
6. Place the order; the customer is taken to My Orders.
7. Use Track Order and enter the order ID to see the current status.
8. Use Returns / Refunds to submit and view return/refund requests.

Order tracking

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
