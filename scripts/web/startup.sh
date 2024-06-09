#!/usr/bin/env bash

echo "Start service"

# migrate database
python scripts/migrate.py

# load fixtures
# python scripts/load_data.py fixture/sirius/sirius.users.json fixture/sirius/sirius.memes.json fixture/sirius/sirius.memes_carts.json fixture/sirius/sirius.memes_ratings.json

exec uvicorn webapp.main:create_app --host=$BIND_IP --port=$BIND_PORT