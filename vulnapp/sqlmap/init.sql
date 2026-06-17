CREATE DATABASE IF NOT EXISTS dvwa;
USE dvwa;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100)
);

INSERT INTO users (username, password, email) VALUES
('admin', 'password123', 'admin@example.com'),
('bob', 'letmein', 'bob@example.com'),
('alice', 'qwerty', 'alice@example.com');