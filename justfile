set dotenv-load

local port='8283':
    uv run uvicorn app:app --reload --host localhost --port {{port}}
