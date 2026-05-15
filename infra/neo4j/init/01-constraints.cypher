// ── Unique constraints ─────────────────────────────────────────────────────
CREATE CONSTRAINT chip_id_unique     IF NOT EXISTS FOR (n:Chip)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT board_id_unique    IF NOT EXISTS FOR (n:Board)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT module_id_unique   IF NOT EXISTS FOR (n:Module)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT fault_id_unique    IF NOT EXISTS FOR (n:FaultPattern) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (n:Document)    REQUIRE n.id IS UNIQUE;

// ── Property existence constraints ────────────────────────────────────────
CREATE CONSTRAINT chip_name_exists   IF NOT EXISTS FOR (n:Chip)  REQUIRE n.name IS NOT NULL;
CREATE CONSTRAINT board_name_exists  IF NOT EXISTS FOR (n:Board) REQUIRE n.name IS NOT NULL;

// ── Full-text indexes (for fuzzy name lookup in M09) ──────────────────────
CREATE FULLTEXT INDEX chip_name_fulltext  IF NOT EXISTS FOR (n:Chip)  ON EACH [n.name, n.aliases];
CREATE FULLTEXT INDEX board_name_fulltext IF NOT EXISTS FOR (n:Board) ON EACH [n.name, n.aliases];

// ── Range indexes for numeric / date queries ──────────────────────────────
CREATE INDEX chip_family_idx  IF NOT EXISTS FOR (n:Chip)  ON (n.family);
CREATE INDEX fault_tags_idx   IF NOT EXISTS FOR (n:FaultPattern) ON (n.symptom_tags);
