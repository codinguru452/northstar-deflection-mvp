USE northstar_db;

CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(190) NOT NULL UNIQUE,
    full_name VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE CASCADE
);

INSERT INTO admin_users (username, email, full_name, password_hash)
VALUES (
    'admin',
    'admin@northstar.co.ke',
    'Northstar Administrator',
    'pbkdf2_sha256$120000$34ab68a5cfb3dfcb9ee7e0bfe73a5e21$dce283b7efdf523c3203d393e75fcb9d666b4cc8295334e78ad7e9105ac71e61'
)
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);
