-- P0 "mastery chỉ từ server": which server path wrote user_flags.mastery_no_efund_invest
-- ('academy' = KUAT graded on the server, 'seed' = demo seed, 'internal' = other server code).
-- Existing rows keep NULL = unproven (they may have been self-set through the removed
-- PATCH /users/{id}/mastery) and are read as not_started until rewritten by a trusted path.
ALTER TABLE user_flags ADD COLUMN mastery_source TEXT;
