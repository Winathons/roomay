# Independent, non-mutating Vapi FUNCTION tool service.
# Never deploy over or replace the Railway Remi TTS service (Dockerfile.voice).
FROM python:3.13.5-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements-voice.txt /app/requirements-voice.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    -r /app/requirements-voice.txt

# The intent router imports domain.conversation_intake and its pure domain contracts.
# No UI, backend, tests, credentials, or hosted Workpeg client is included.
COPY domain/ /app/domain/
COPY voice_adapter/ /app/voice_adapter/

# The webhook needs only read access to its code and writes no local state.
USER 10001:10001

EXPOSE 8080

# One process keeps the in-memory replay/rate limit state consistent per instance.
# Edge-level rate limits and shared replay protection are required for scaled hosting.
CMD ["sh", "-c", "exec gunicorn voice_adapter.tool_wsgi:application --bind 0.0.0.0:${PORT:-8080} --worker-class gthread --workers 1 --threads 2 --backlog 16 --limit-request-line 4094 --limit-request-fields 64 --limit-request-field_size 4096 --timeout 30 --graceful-timeout 15 --access-logfile - --access-logformat '%(m)s %(U)s %(s)s %(L)s'"]
