#!/bin/sh
# Initialise the IRIS sidecar (same replica, localhost) with the demo patients, then start the API.
cd /app/backend
python /app/boot.py &
BOOT=$!
# Mailpit is a sidecar in this replica, not host "mailpit".
sed -i 's|Name="SMTPServer">mailpit|Name="SMTPServer">localhost|' /app/iris/src/PacsComparator/Production.cls
set -x
timeout 1500 python scripts/iris_setup.py --timeout 900 || echo "iris_setup failed"
timeout 900 python scripts/load_iris.py --demo --workers 2 || echo "load_iris failed"
timeout 1800 python scripts/run_review.py --random 0 || echo "run_review failed"
timeout 900 python scripts/seed_hospitals.py || echo "seed_hospitals failed"
timeout 1800 python scripts/demo_reset.py || echo "demo_reset failed"
timeout 900 python scripts/sql_projection_setup.py || echo "sql_projection_setup failed"
set +x
kill $BOOT 2>/dev/null
sleep 1
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
