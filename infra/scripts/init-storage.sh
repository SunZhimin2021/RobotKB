#!/usr/bin/env bash
# Initialise storage services after docker compose up.
# Run from the project root: bash infra/scripts/init-storage.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# ── Load .env ──────────────────────────────────────────────────────────────────
if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "⚠️  .env not found — copy .env.example to .env and fill in passwords" >&2
  exit 1
fi

: "${MEILI_MASTER_KEY:?MEILI_MASTER_KEY must be set in .env}"
: "${POSTGRES_USER:=robotkb}"
: "${POSTGRES_DB:=robotkb}"
: "${NEO4J_AUTH:=neo4j/changeme}"
NEO4J_PASSWORD="${NEO4J_AUTH#*/}"

# ── Wait for container to report healthy ──────────────────────────────────────
wait_healthy() {
  local name="$1"
  local max=40   # 40 × 3s = 2 min
  local i=0
  printf '⏳ Waiting for %s ' "$name"
  while [ $i -lt $max ]; do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ]; then
      echo "✅"
      return 0
    fi
    printf '.'
    sleep 3
    i=$((i+1))
  done
  echo " ❌"
  echo "Error: $name did not become healthy within $((max*3))s" >&2
  docker inspect --format='{{json .State.Health}}' "$name" 2>/dev/null | python3 -m json.tool || true
  exit 1
}

wait_healthy robotkb-postgres
wait_healthy robotkb-meilisearch
wait_healthy robotkb-neo4j

# ── Meilisearch: create index + apply settings ────────────────────────────────
echo "📋 Configuring Meilisearch index 'chunks'..."

# Create index (ignore 409 if already exists)
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:7700/indexes" \
  -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"uid":"chunks","primaryKey":"id"}')
[ "$HTTP_STATUS" = "202" ] || [ "$HTTP_STATUS" = "409" ] || {
  echo "Error: Meilisearch index creation returned HTTP $HTTP_STATUS" >&2
  exit 1
}

# Apply settings
curl -sf -X PATCH "http://localhost:7700/indexes/chunks/settings" \
  -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d @infra/meilisearch/chunks-settings.json > /dev/null
echo "✅ Meilisearch 'chunks' index configured"

# ── Neo4j: apply constraints + indexes ────────────────────────────────────────
echo "📋 Applying Neo4j schema constraints..."
docker exec -i robotkb-neo4j \
  cypher-shell -u neo4j -p "${NEO4J_PASSWORD}" \
  < infra/neo4j/init/01-constraints.cypher
echo "✅ Neo4j constraints applied"

# ── PostgreSQL: verify extensions ─────────────────────────────────────────────
echo "📋 Verifying PostgreSQL extensions..."
docker exec robotkb-postgres \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','uuid-ossp') ORDER BY extname;"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          RobotKB Storage Services Ready                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  PostgreSQL    localhost:5432   DB: %-19s ║\n" "${POSTGRES_DB}"
echo "║  Meilisearch   http://localhost:7700                     ║"
echo "║  Neo4j HTTP    http://localhost:7474                     ║"
echo "║  Neo4j Bolt    bolt://localhost:7687                     ║"
echo "║  MinIO API     http://localhost:9000                     ║"
echo "║  MinIO UI      http://localhost:9001                     ║"
echo "║  Redis         localhost:6379                            ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  From dev machine: replace localhost with 192.168.3.58   ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Next step (M08): pytest src/storage/tests/              ║"
echo "╚══════════════════════════════════════════════════════════╝"
