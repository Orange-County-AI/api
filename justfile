set dotenv-load

local:
    uv run uvicorn app:app --reload --host localhost --port 8000
