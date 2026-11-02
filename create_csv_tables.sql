CREATE TABLE IF NOT EXISTS csv_uploads (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    report_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_count INT UNSIGNED NOT NULL,
    date_from DATE NULL,
    date_to DATE NULL,
    column_mapping JSON NOT NULL,
    notes TEXT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS csv_upload_rows (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    upload_id BIGINT UNSIGNED NOT NULL,
    row_number INT UNSIGNED NOT NULL,
    row_data JSON NOT NULL,
    PRIMARY KEY (id),
    KEY idx_csv_upload_rows_upload_id (upload_id),
    CONSTRAINT fk_csv_upload_rows_upload
        FOREIGN KEY (upload_id) REFERENCES csv_uploads (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
