USE northstar_db;

-- Run this ONCE if you already created admin_users using the previous setup.
ALTER TABLE admin_users
    ADD COLUMN email VARCHAR(190) NULL UNIQUE AFTER username;

UPDATE admin_users
SET email = 'admin@northstar.co.ke'
WHERE username = 'admin' AND (email IS NULL OR email = '');

-- The admin login now uses the email address.
