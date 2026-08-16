USE northstar_db;

-- Expand Northstar order tracking from a simple delivery status to realistic logistics milestones.
ALTER TABLE orders
  MODIFY COLUMN status ENUM(
    'Order Placed',
    'Payment Confirmed',
    'Processing',
    'Packed',
    'Handed to Courier',
    'In Transit',
    'Arrived at Local Hub',
    'Out for Delivery',
    'Delivered',
    'Cancelled'
  ) NOT NULL DEFAULT 'Order Placed',
  ADD COLUMN tracking_number VARCHAR(40) NULL UNIQUE AFTER order_number,
  ADD COLUMN estimated_delivery_date DATE NULL AFTER tracking_number;

-- Give existing orders a tracking number and an estimated delivery date.
UPDATE orders
SET tracking_number = CONCAT('NST-KE-', UPPER(SUBSTRING(REPLACE(UUID(), '-', ''), 1, 8)))
WHERE tracking_number IS NULL;

UPDATE orders
SET estimated_delivery_date = DATE_ADD(DATE(created_at), INTERVAL 6 DAY)
WHERE estimated_delivery_date IS NULL;

-- Existing orders retain their current status. New orders will receive
-- tracking numbers and dates automatically from backend.py.
