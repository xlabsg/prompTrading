-- Make invite_id nullable in pending_oauth table to support login without invite code
-- Users can login with existing OAuth accounts without providing an invite code
-- Invite code is only required for new user registration

ALTER TABLE pending_oauth
ALTER COLUMN invite_id DROP NOT NULL;
