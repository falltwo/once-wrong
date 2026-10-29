-- Additive normalized storage for the existing reports/versions API.
-- Every writer must register database.register_functions and enable foreign_keys.
CREATE TABLE IF NOT EXISTS dataset_type (
    code TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    file_kind TEXT NOT NULL,
    name TEXT NOT NULL,
    key_fields TEXT NOT NULL CHECK(json_valid(key_fields) AND json_type(key_fields)='array'),
    group_fields TEXT CHECK(group_fields IS NULL OR json_type(group_fields)='array')
) STRICT;
CREATE TABLE IF NOT EXISTS rule_set (
    id INTEGER PRIMARY KEY,
    profile_id TEXT NOT NULL,
    version_label TEXT NOT NULL,
    manual_title TEXT NOT NULL,
    manual_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(profile_id,version_label)
) STRICT;
CREATE TABLE IF NOT EXISTS rule (
    id INTEGER PRIMARY KEY,
    rule_set_id INTEGER NOT NULL REFERENCES rule_set(id),
    code TEXT NOT NULL,
    dataset_type TEXT NOT NULL REFERENCES dataset_type(code),
    title TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('single_record','multi_record','cross_file')),
    severity TEXT NOT NULL CHECK(severity IN ('error','warning')),
    handler TEXT NOT NULL,
    params TEXT NOT NULL CHECK(json_valid(params) AND json_type(params)='object'),
    issue_key_level TEXT NOT NULL CHECK(issue_key_level IN ('record','group')),
    manual_page TEXT NOT NULL,
    UNIQUE(rule_set_id,code,dataset_type)
) STRICT;
CREATE TABLE IF NOT EXISTS version_state (
    version_id TEXT PRIMARY KEY REFERENCES versions(id),
    profile_id TEXT NOT NULL,
    rule_set_id INTEGER NOT NULL REFERENCES rule_set(id),
    manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
    file_count INTEGER NOT NULL CHECK(file_count>0),
    record_count INTEGER NOT NULL CHECK(record_count>=0),
    issue_count INTEGER NOT NULL CHECK(issue_count>=0),
    not_evaluated_checks INTEGER NOT NULL CHECK(not_evaluated_checks>=0),
    sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0,1))
) STRICT;
CREATE TABLE IF NOT EXISTS version_file (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES versions(id),
    dataset_type TEXT NOT NULL REFERENCES dataset_type(code),
    filename TEXT NOT NULL,
    source_bytes BLOB NOT NULL,
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
    columns_json TEXT NOT NULL CHECK(json_valid(columns_json)),
    UNIQUE(version_id,dataset_type)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_version_file_version ON version_file(version_id);
CREATE TABLE IF NOT EXISTS record (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES versions(id),
    file_id TEXT NOT NULL REFERENCES version_file(id),
    line_no INTEGER NOT NULL CHECK(line_no>=1),
    api_row_id TEXT NOT NULL,
    record_key TEXT NOT NULL CHECK(json_type(record_key)='array'),
    group_key TEXT CHECK(group_key IS NULL OR json_type(group_key)='array'),
    fields TEXT NOT NULL CHECK(json_type(fields)='object'),
    raw_line TEXT NOT NULL,
    UNIQUE(file_id,line_no),
    UNIQUE(file_id,api_row_id)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_record_version ON record(version_id);
CREATE INDEX IF NOT EXISTS idx_record_key ON record(version_id,file_id,record_key);
CREATE INDEX IF NOT EXISTS idx_record_group ON record(version_id,file_id,group_key);
CREATE TABLE IF NOT EXISTS issue (
    id TEXT PRIMARY KEY,
    api_id TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES versions(id),
    report_id TEXT NOT NULL REFERENCES reports(id),
    version_number INTEGER NOT NULL,
    profile_id TEXT NOT NULL,
    rule_id INTEGER NOT NULL REFERENCES rule(id),
    issue_key TEXT NOT NULL,
    message TEXT NOT NULL,
    facts TEXT NOT NULL CHECK(json_type(facts)='object'),
    repeat_status TEXT NOT NULL CHECK(repeat_status IN ('new','repeated','regressed')),
    prev_seen_number INTEGER,
    first_seen_number INTEGER NOT NULL,
    UNIQUE(version_id,api_id),
    CHECK(prev_seen_number IS NULL OR prev_seen_number BETWEEN 1 AND version_number-1),
    CHECK(first_seen_number BETWEEN 1 AND version_number),
    CHECK((repeat_status='new')=(prev_seen_number IS NULL)),
    CHECK((repeat_status='repeated')=(prev_seen_number IS NOT NULL AND prev_seen_number=version_number-1)),
    CHECK((repeat_status='new')=(first_seen_number=version_number))
) STRICT;
CREATE INDEX IF NOT EXISTS idx_issue_history ON issue(report_id,profile_id,issue_key,version_number);
CREATE INDEX IF NOT EXISTS idx_issue_version ON issue(version_id);
CREATE TABLE IF NOT EXISTS issue_cell (
    issue_id TEXT NOT NULL REFERENCES issue(id),
    record_id TEXT NOT NULL REFERENCES record(id),
    field_name TEXT NOT NULL,
    PRIMARY KEY(issue_id,record_id,field_name)
) STRICT, WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS issue_context (
    issue_id TEXT NOT NULL REFERENCES issue(id),
    record_id TEXT NOT NULL REFERENCES record(id),
    PRIMARY KEY(issue_id,record_id)
) STRICT, WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS ai_review (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL REFERENCES issue(id),
    model TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('ai','fallback_llm_error','fallback_number_guard')),
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    blocked_numbers TEXT NOT NULL CHECK(json_type(blocked_numbers)='array'),
    created_at TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_ai_review_issue ON ai_review(issue_id,created_at);
CREATE TABLE IF NOT EXISTS suggestion (
    id INTEGER PRIMARY KEY,
    ai_review_id TEXT NOT NULL REFERENCES ai_review(id),
    rank INTEGER NOT NULL CHECK(rank>=1),
    reason TEXT NOT NULL,
    revalidation TEXT NOT NULL CHECK(revalidation IN ('passed','failed','invalid_target')),
    rejection_reason TEXT,
    candidate_json TEXT NOT NULL CHECK(json_type(candidate_json)='object'),
    UNIQUE(ai_review_id,rank),
    CHECK((revalidation='passed')=(rejection_reason IS NULL))
) STRICT;
CREATE TABLE IF NOT EXISTS suggestion_change (
    suggestion_id INTEGER NOT NULL REFERENCES suggestion(id),
    record_id TEXT NOT NULL REFERENCES record(id),
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    PRIMARY KEY(suggestion_id,record_id,field_name)
) STRICT, WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS citation (
    ai_review_id TEXT NOT NULL REFERENCES ai_review(id),
    passage_id TEXT NOT NULL,
    source_title TEXT NOT NULL,
    section TEXT NOT NULL,
    page TEXT NOT NULL,
    PRIMARY KEY(ai_review_id,passage_id)
) STRICT, WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS audit_event (
    id INTEGER PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    version_id TEXT REFERENCES versions(id),
    issue_id TEXT REFERENCES issue(id),
    payload TEXT NOT NULL CHECK(json_type(payload)='object'),
    prev_hash TEXT NOT NULL UNIQUE CHECK(length(prev_hash)=64),
    hash TEXT NOT NULL UNIQUE CHECK(length(hash)=64)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_audit_version ON audit_event(version_id,id);

CREATE TRIGGER IF NOT EXISTS trg_versions_sequence BEFORE INSERT ON versions
WHEN NEW.number<>COALESCE((SELECT max(number) FROM versions WHERE report_id=NEW.report_id),0)+1
BEGIN SELECT RAISE(ABORT,'version number must be previous max + 1'); END;
CREATE TRIGGER IF NOT EXISTS trg_versions_no_update BEFORE UPDATE ON versions
BEGIN SELECT RAISE(ABORT,'version is immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_versions_no_delete BEFORE DELETE ON versions
BEGIN SELECT RAISE(ABORT,'version is immutable'); END;

CREATE TRIGGER IF NOT EXISTS trg_state_match BEFORE INSERT ON version_state
WHEN NEW.sealed<>0
 OR NEW.profile_id<>json_extract((SELECT payload_json FROM versions WHERE id=NEW.version_id),'$.schemaProfileId')
 OR NEW.not_evaluated_checks<>json_extract((SELECT payload_json FROM versions WHERE id=NEW.version_id),'$.summary.notEvaluatedChecks')
 OR (SELECT version_label FROM rule_set WHERE id=NEW.rule_set_id)<>json_extract((SELECT payload_json FROM versions WHERE id=NEW.version_id),'$.ruleVersion')
BEGIN SELECT RAISE(ABORT,'version state does not match snapshot'); END;
CREATE TRIGGER IF NOT EXISTS trg_state_seal BEFORE UPDATE ON version_state
WHEN OLD.sealed<>0 OR NEW.sealed<>1
 OR NEW.version_id<>OLD.version_id OR NEW.profile_id<>OLD.profile_id
 OR NEW.rule_set_id<>OLD.rule_set_id OR NEW.manifest_sha256<>OLD.manifest_sha256
 OR NEW.file_count<>OLD.file_count OR NEW.record_count<>OLD.record_count
 OR NEW.issue_count<>OLD.issue_count OR NEW.not_evaluated_checks<>OLD.not_evaluated_checks
 OR NEW.file_count<>(SELECT count(*) FROM version_file WHERE version_id=OLD.version_id)
 OR NEW.record_count<>(SELECT count(*) FROM record WHERE version_id=OLD.version_id)
 OR NEW.issue_count<>(SELECT count(*) FROM issue WHERE version_id=OLD.version_id)
 OR EXISTS(SELECT 1 FROM issue AS i WHERE i.version_id=OLD.version_id AND NOT EXISTS(SELECT 1 FROM issue_cell WHERE issue_id=i.id))
 OR EXISTS(SELECT 1 FROM version_file WHERE version_id=OLD.version_id AND sha256(source_bytes)<>source_sha256)
 OR NEW.manifest_sha256<>(SELECT manifest_hash(json_group_array(json_object('datasetType',dataset_type,'sourceSha256',source_sha256))) FROM version_file WHERE version_id=OLD.version_id)
BEGIN SELECT RAISE(ABORT,'version state may only seal complete immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS trg_state_no_delete BEFORE DELETE ON version_state
BEGIN SELECT RAISE(ABORT,'version state is immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_file_open BEFORE INSERT ON version_file
WHEN COALESCE((SELECT sealed FROM version_state WHERE version_id=NEW.version_id),1)<>0
 OR sha256(NEW.source_bytes)<>NEW.source_sha256
BEGIN SELECT RAISE(ABORT,'file must belong to an open version and match hash'); END;
CREATE TRIGGER IF NOT EXISTS trg_record_consistency BEFORE INSERT ON record
WHEN COALESCE((SELECT sealed FROM version_state WHERE version_id=NEW.version_id),1)<>0
 OR NEW.version_id<>(SELECT version_id FROM version_file WHERE id=NEW.file_id)
 OR EXISTS(SELECT 1 FROM json_each(NEW.fields) WHERE type<>'text')
 OR EXISTS(SELECT 1 FROM json_each((SELECT key_fields FROM dataset_type WHERE code=(SELECT dataset_type FROM version_file WHERE id=NEW.file_id))) AS k WHERE NOT EXISTS(SELECT 1 FROM json_each(NEW.fields) AS f WHERE f.key=k.value))
 OR json(NEW.record_key)<>(SELECT json_group_array(value) FROM (SELECT json_extract(NEW.fields,'$.'||json_quote(k.value)) AS value FROM json_each((SELECT key_fields FROM dataset_type WHERE code=(SELECT dataset_type FROM version_file WHERE id=NEW.file_id))) AS k ORDER BY k.key))
 OR json(NEW.group_key) IS NOT (SELECT CASE WHEN d.group_fields IS NULL THEN NULL ELSE (SELECT json_group_array(value) FROM (SELECT json_extract(NEW.fields,'$.'||json_quote(g.value)) AS value FROM json_each(d.group_fields) AS g ORDER BY g.key)) END FROM dataset_type AS d WHERE d.code=(SELECT dataset_type FROM version_file WHERE id=NEW.file_id))
BEGIN SELECT RAISE(ABORT,'record keys or file/version are inconsistent'); END;
CREATE TRIGGER IF NOT EXISTS trg_issue_consistency BEFORE INSERT ON issue
WHEN COALESCE((SELECT sealed FROM version_state WHERE version_id=NEW.version_id),1)<>0
 OR NEW.report_id<>(SELECT report_id FROM versions WHERE id=NEW.version_id)
 OR NEW.version_number<>(SELECT number FROM versions WHERE id=NEW.version_id)
 OR NEW.profile_id<>(SELECT profile_id FROM version_state WHERE version_id=NEW.version_id)
 OR (SELECT rule_set_id FROM rule WHERE id=NEW.rule_id)<>(SELECT rule_set_id FROM version_state WHERE version_id=NEW.version_id)
BEGIN SELECT RAISE(ABORT,'issue does not match open version or rule set'); END;
CREATE TRIGGER IF NOT EXISTS trg_issue_history BEFORE INSERT ON issue
WHEN NEW.prev_seen_number IS NOT (
 SELECT max(i.version_number) FROM issue AS i
 WHERE i.report_id=NEW.report_id AND i.profile_id=NEW.profile_id AND i.issue_key=NEW.issue_key
 AND i.version_number<NEW.version_number
 AND i.version_number>COALESCE((SELECT max(v.number) FROM versions AS v WHERE v.report_id=NEW.report_id AND v.number<NEW.version_number AND json_extract(v.payload_json,'$.schemaProfileId')<>NEW.profile_id),0))
 OR NEW.first_seen_number<>COALESCE((
 SELECT min(i.version_number) FROM issue AS i
 WHERE i.report_id=NEW.report_id AND i.profile_id=NEW.profile_id AND i.issue_key=NEW.issue_key
 AND i.version_number<NEW.version_number
 AND i.version_number>COALESCE((SELECT max(v.number) FROM versions AS v WHERE v.report_id=NEW.report_id AND v.number<NEW.version_number AND json_extract(v.payload_json,'$.schemaProfileId')<>NEW.profile_id),0)),NEW.version_number)
BEGIN SELECT RAISE(ABORT,'issue history is inconsistent'); END;
CREATE TRIGGER IF NOT EXISTS trg_issue_cell_consistency BEFORE INSERT ON issue_cell
WHEN (SELECT version_id FROM issue WHERE id=NEW.issue_id)<>(SELECT version_id FROM record WHERE id=NEW.record_id)
 OR COALESCE((SELECT sealed FROM version_state WHERE version_id=(SELECT version_id FROM issue WHERE id=NEW.issue_id)),1)<>0
 OR NOT EXISTS(SELECT 1 FROM json_each((SELECT fields FROM record WHERE id=NEW.record_id)) WHERE key=NEW.field_name)
 OR EXISTS(SELECT 1 FROM issue AS i JOIN rule AS r ON r.id=i.rule_id JOIN record AS rec ON rec.id=NEW.record_id JOIN version_file AS f ON f.id=rec.file_id WHERE i.id=NEW.issue_id AND r.scope<>'cross_file' AND r.dataset_type<>f.dataset_type)
BEGIN SELECT RAISE(ABORT,'issue cell must be an existing field of the same open version'); END;
CREATE TRIGGER IF NOT EXISTS trg_issue_context_consistency BEFORE INSERT ON issue_context
WHEN (SELECT version_id FROM issue WHERE id=NEW.issue_id)<>(SELECT version_id FROM record WHERE id=NEW.record_id)
 OR COALESCE((SELECT sealed FROM version_state WHERE version_id=(SELECT version_id FROM issue WHERE id=NEW.issue_id)),1)<>0
 OR EXISTS(SELECT 1 FROM issue AS i JOIN rule AS r ON r.id=i.rule_id JOIN record AS rec ON rec.id=NEW.record_id JOIN version_file AS f ON f.id=rec.file_id WHERE i.id=NEW.issue_id AND r.scope<>'cross_file' AND r.dataset_type<>f.dataset_type)
BEGIN SELECT RAISE(ABORT,'context must belong to the same open version'); END;
CREATE TRIGGER IF NOT EXISTS trg_ai_review_sealed BEFORE INSERT ON ai_review
WHEN COALESCE((SELECT sealed FROM version_state WHERE version_id=(SELECT version_id FROM issue WHERE id=NEW.issue_id)),0)<>1
BEGIN SELECT RAISE(ABORT,'AI review requires a sealed version'); END;
CREATE TRIGGER IF NOT EXISTS trg_suggestion_target BEFORE INSERT ON suggestion_change
WHEN (SELECT version_id FROM record WHERE id=NEW.record_id) IS NOT (SELECT i.version_id FROM issue AS i JOIN ai_review AS a ON a.issue_id=i.id JOIN suggestion AS s ON s.ai_review_id=a.id WHERE s.id=NEW.suggestion_id)
 OR NOT EXISTS(SELECT 1 FROM json_each((SELECT fields FROM record WHERE id=NEW.record_id)) WHERE key=NEW.field_name)
 OR ((SELECT revalidation FROM suggestion WHERE id=NEW.suggestion_id)='passed'
 AND NOT EXISTS(SELECT 1 FROM issue_cell AS c JOIN ai_review AS a ON a.issue_id=c.issue_id JOIN suggestion AS s ON s.ai_review_id=a.id WHERE s.id=NEW.suggestion_id AND c.record_id=NEW.record_id AND c.field_name=NEW.field_name)
 )
BEGIN SELECT RAISE(ABORT,'passed candidate may only change issue cells'); END;
CREATE TRIGGER IF NOT EXISTS trg_confirmation_checks BEFORE INSERT ON confirmations
WHEN NEW.version_id<>(SELECT id FROM versions WHERE report_id=NEW.report_id ORDER BY number DESC LIMIT 1)
 OR NEW.report_id<>(SELECT report_id FROM versions WHERE id=NEW.version_id)
 OR COALESCE((SELECT sealed FROM version_state WHERE version_id=NEW.version_id),0)<>1
 OR COALESCE((SELECT not_evaluated_checks FROM version_state WHERE version_id=NEW.version_id),1)<>0
 OR EXISTS(SELECT 1 FROM issue AS i JOIN rule AS r ON r.id=i.rule_id WHERE i.version_id=NEW.version_id AND r.severity='error')
 OR NEW.source_sha256<>(SELECT source_sha256 FROM versions WHERE id=NEW.version_id)
 OR NEW.source_sha256<>sha256((SELECT source_bytes FROM versions WHERE id=NEW.version_id))
 OR NEW.rule_version<>json_extract((SELECT payload_json FROM versions WHERE id=NEW.version_id),'$.ruleVersion')
 OR EXISTS(SELECT 1 FROM version_file WHERE version_id=NEW.version_id AND source_sha256<>sha256(source_bytes))
 OR (SELECT manifest_sha256 FROM version_state WHERE version_id=NEW.version_id)<>(SELECT manifest_hash(json_group_array(json_object('datasetType',dataset_type,'sourceSha256',source_sha256))) FROM version_file WHERE version_id=NEW.version_id)
BEGIN SELECT RAISE(ABORT,'confirmation requires latest complete zero-error version and matching hashes'); END;
CREATE TRIGGER IF NOT EXISTS trg_rule_group_supported BEFORE INSERT ON rule
WHEN NEW.issue_key_level='group' AND (SELECT group_fields FROM dataset_type WHERE code=NEW.dataset_type) IS NULL
BEGIN SELECT RAISE(ABORT,'group rule requires policy fields'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_chain BEFORE INSERT ON audit_event
WHEN NEW.prev_hash<>COALESCE((SELECT hash FROM audit_event ORDER BY id DESC LIMIT 1),printf('%064d',0))
 OR NEW.hash<>audit_hash(NEW.prev_hash,NEW.occurred_at,NEW.actor,NEW.event_type,NEW.version_id,NEW.issue_id,NEW.payload)
 OR (NEW.issue_id IS NOT NULL AND NEW.version_id IS NOT (SELECT version_id FROM issue WHERE id=NEW.issue_id))
BEGIN SELECT RAISE(ABORT,'audit event must extend the unique valid chain'); END;
