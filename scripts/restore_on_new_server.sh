#!/usr/bin/env bash
# restore_on_new_server.sh
# Restores a snapshot made by the GitHub workflow onto a NEW server's MySQL.
#
# Usage:
#   export BACKUP_SECRET_KEY='same secret as in GitHub'
#   export DB_ROOT_PASS='mysql root password of the new server'      # optional if root has no password
#   ./restore_on_new_server.sh db_snapshot_XXXX.sql.gz.enc [license.key.enc]
#
# Optional env: DB_NAME (default local_django_db), DB_USER (default root), DB_HOST (127.0.0.1), DB_PORT (3306)
set -euo pipefail

SNAP="${1:-}"
LIC="${2:-}"
DB_NAME="${DB_NAME:-local_django_db}"
DB_USER="${DB_USER:-root}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
export MYSQL_PWD="${DB_ROOT_PASS:-}"

if [ -z "$SNAP" ] || [ ! -f "$SNAP" ]; then
  echo "Usage: $0 <db_snapshot_....sql.gz.enc> [license.key.enc]"; exit 1
fi
if [ -z "${BACKUP_SECRET_KEY:-}" ]; then
  echo "BACKUP_SECRET_KEY is not set. Run: export BACKUP_SECRET_KEY='...'"; exit 1
fi
command -v mysql >/dev/null || { echo "mysql client not found. Install MySQL 8.4 first."; exit 1; }
python3 -c "import cryptography" 2>/dev/null || { echo "Installing 'cryptography'..."; pip install cryptography; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# same Fernet scheme the workflow uses
cat > "$WORK/crypt.py" <<'PYEOF'
import base64, os, sys
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                 salt=b'django_backup_salt_2026', iterations=100000)
f = Fernet(base64.urlsafe_b64encode(kdf.derive(os.environ['BACKUP_SECRET_KEY'].encode())))
data = open(src, 'rb').read()
open(dst, 'wb').write(f.encrypt(data) if mode == 'enc' else f.decrypt(data))
PYEOF

echo "1/4  Decrypting snapshot..."
python3 "$WORK/crypt.py" dec "$SNAP" "$WORK/restored.sql.gz" || { echo "Decrypt FAILED - wrong BACKUP_SECRET_KEY or damaged file."; exit 1; }
gunzip -c "$WORK/restored.sql.gz" > "$WORK/restored.sql"
echo "     SQL size: $(stat -c %s "$WORK/restored.sql") bytes"

M=(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER")

if "${M[@]}" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null | grep -qv '^0$'; then
  echo "WARNING: database '$DB_NAME' already has tables on this server."
  read -r -p "Type YES to ERASE it and restore the snapshot: " A
  [ "$A" = "YES" ] || { echo "Cancelled."; exit 1; }
fi

echo "2/4  Creating database '$DB_NAME'..."
"${M[@]}" -e "DROP DATABASE IF EXISTS \`$DB_NAME\`; CREATE DATABASE \`$DB_NAME\` CHARACTER SET utf8mb4;"

echo "3/4  Importing data (may take a few minutes)..."
"${M[@]}" "$DB_NAME" < "$WORK/restored.sql"
TABLES=$("${M[@]}" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';")
echo "     Done: $TABLES tables loaded."

echo "4/4  License file..."
if [ -n "$LIC" ] && [ -f "$LIC" ]; then
  python3 "$WORK/crypt.py" dec "$LIC" ./license.key && echo "     license.key written to $(pwd)"
else
  echo "     (no license.key.enc given - skipped)"
fi

cat <<MSG

Restore finished. Next on the new server:
  1) put the project code there and set the SAME secrets in its environment
     (DJANGO_SECRET_KEY, DJANGO_SALT_KEY, LICENSE_MACHINE_SEED, Cloudinary keys, ...)
  2) python manage.py migrate
  3) python manage.py collectstatic --noinput
  4) start the site, test login / latest order / images / license
  5) only then point the domain (DNS) to the new server and keep the old GitHub workflow OFF
MSG
