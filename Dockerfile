FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system fleetops && adduser --system --ingroup fleetops fleetops

COPY pyproject.toml README.md LICENSE /app/
COPY fleetops /app/fleetops

RUN pip install --no-cache-dir .

RUN mkdir -p /tmp/fleetops && chown -R fleetops:fleetops /tmp/fleetops

USER fleetops

CMD ["fleetops"]

