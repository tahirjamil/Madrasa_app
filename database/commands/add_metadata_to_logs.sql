-- Add metadata column to logs table for enhanced logging
-- This migration adds support for structured logging with additional metadata

ALTER TABLE logs ADD COLUMN metadata JSON DEFAULT NULL;

-- Add index for better performance on metadata queries
CREATE INDEX idx_logs_metadata ON logs ((metadata->>'level'));
CREATE INDEX idx_logs_timestamp ON logs (created_at);

-- Update existing logs to have basic metadata
UPDATE logs SET metadata = JSON_OBJECT(
    'level', 'INFO',
    'action', action,
    'phone', phone,
    'message', message,
    'timestamp', DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.000Z')
) WHERE metadata IS NULL; 