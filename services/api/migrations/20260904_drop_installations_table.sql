-- Drop the orphaned installations table and the Repository FK that pointed at it.
--
-- Nothing ever read or wrote either one: the GitHub App flow stores GitHub's
-- raw installation id in repositories.github_installation_id, a plain string
-- column, and resolves tokens from that. repositories.installation_id was
-- always NULL.

ALTER TABLE repositories
    DROP COLUMN IF EXISTS installation_id;

DROP TABLE IF EXISTS installations;
