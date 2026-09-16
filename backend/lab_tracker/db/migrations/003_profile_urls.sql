-- The migration runner preflights conflicts and makes a SQLite backup before this transaction.
UPDATE professors
SET lab_url = select_personal_url(directory_profile_url, homepage_url, lab_url);

UPDATE update_proposals
SET old_values_json = convert_profile_snapshot(old_values_json),
    new_values_json = convert_profile_snapshot(new_values_json);

ALTER TABLE professors RENAME COLUMN directory_profile_url TO official_profile_url;
ALTER TABLE professors DROP COLUMN homepage_url;
ALTER TABLE professors RENAME COLUMN lab_url TO personal_homepage_url;
