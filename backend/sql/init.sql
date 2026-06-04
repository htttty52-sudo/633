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
    INDEX idx_last_heartbeat (last_heartbeat),
    INDEX idx_model_kernel (model, kernel_version)
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
    drift_field_count INT NOT NULL DEFAULT 0,
    bound_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_template_device (template_id, device_id),
    FOREIGN KEY (template_id) REFERENCES config_templates(id),
    FOREIGN KEY (device_id) REFERENCES devices(device_id),
    INDEX idx_binding_device (device_id),
    INDEX idx_binding_template (template_id),
    INDEX idx_binding_hashes (device_id, expected_config_hash, current_config_hash),
    INDEX idx_binding_drift_fields (drift_field_count)
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

CREATE TABLE IF NOT EXISTS firmwares (
    id INT AUTO_INCREMENT PRIMARY KEY,
    version VARCHAR(64) NOT NULL UNIQUE,
    target_model VARCHAR(128) NOT NULL,
    filename VARCHAR(256) NOT NULL,
    file_size INT NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    description VARCHAR(512) DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_firmware_version (version),
    INDEX idx_firmware_model (target_model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ota_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    firmware_id INT NOT NULL,
    target_model VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    total_devices INT NOT NULL,
    batch1_size INT NOT NULL,
    batch2_size INT NOT NULL,
    batch3_size INT NOT NULL,
    current_batch INT DEFAULT 0,
    retry_count INT DEFAULT 0,
    next_retry_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (firmware_id) REFERENCES firmwares(id),
    INDEX idx_ota_task_status (status),
    INDEX idx_ota_task_firmware (firmware_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ota_device_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ota_task_id INT NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    batch_number INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    previous_version VARCHAR(64) NOT NULL,
    target_version VARCHAR(64) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(128) NULL,
    error_message VARCHAR(512),
    started_at DATETIME,
    completed_at DATETIME,
    UNIQUE KEY uq_ota_task_device (ota_task_id, device_id),
    FOREIGN KEY (ota_task_id) REFERENCES ota_tasks(id),
    FOREIGN KEY (device_id) REFERENCES devices(device_id),
    INDEX idx_odt_status (status),
    INDEX idx_odt_task_batch_status (ota_task_id, batch_number, status),
    INDEX idx_odt_idempotency (idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
