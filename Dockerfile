FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

# copy pyproject.toml and uv.lock
COPY pyproject.toml uv.lock ./

# install dependencies
RUN uv sync

# copy the rest of the app
COPY app.py meetup.py ./

# run the app
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8283"]
