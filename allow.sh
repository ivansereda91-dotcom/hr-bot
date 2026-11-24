#!/bin/bash
# Доступ к боту: bash /opt/hr-bot/allow.sh ID1 [ID2 ...]
cd /opt/hr-bot && set -a && . ./.env && set +a
./venv/bin/python -c "import db,sys; db.set_path('$DB_PATH'); db.init(); db.allow(sys.argv[1:]); print('Доступ открыт:', db.allowed_ids())" "$@"
