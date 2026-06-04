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

CREATE TABLE IF NOT EXISTS config_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description VARCHAR(512) DEFAULT '',
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_template_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS template_bindings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_id INT NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    expected_config_hash VARCHAR(64),
    current_config_hash VARCHAR(64),
    bound_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_template_device (template_id, device_id),
    FOREIGN KEY (template_id) REFERENCES config_templates(id),
    FOREIGN KEY (device_id) REFERENCES devices(device_id),
    INDEX idx_binding_device (device_id),
    INDEX idx_binding_template (template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS deployment_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    binding_id INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rendered_content TEXT,
    error_message VARCHAR(512),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY (binding_id) REFERENCES template_bindings(id),
    INDEX idx_deployment_binding (binding_id),
    INDEX idx_deployment_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
