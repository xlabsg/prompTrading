-- Fix jobs.type column length to accommodate longer job type names
-- Issue: 'template_performance_update' (23 chars) exceeds VARCHAR(21) limit
-- Date: 2026-01-25

-- Alter the jobs.type column to VARCHAR(50) to match the model definition
ALTER TABLE jobs ALTER COLUMN type TYPE VARCHAR(50);
