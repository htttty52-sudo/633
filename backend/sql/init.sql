CREATE DATABASE IF NOT EXISTS embedded_linux_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE embedded_linux_platform;

CREATE TABLE IF NOT EXISTS devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL UNIQUE,
    model VARCHAR(128) NOT NULL,
    kernel_version VARCHAR(64) NOT NULL,
    is_online BOOLEAN DEFAULT TRUE,
    last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_device_id (device_id),
    INDEX idx_is_online (is_online),
    INDEX idx_last_heartbeat (last_heartbeat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
