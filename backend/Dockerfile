FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY evaluate.py pytest.ini ./

# SQLite history lives here; mount a volume to keep it between runs.
RUN mkdir -p /app/data

EXPOSE 8000

# NOTE: the default "subprocess" sandbox runs user code inside THIS container.
# That is acceptable for a college project because the container itself is the boundary.
# Do not expose this service to the public internet.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
