FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY tools ./tools

RUN useradd -m appuser
USER appuser

EXPOSE 8000
# Jeden worker: limit logowań trzyma liczniki w pamięci procesu (app/routers/auth.py).
# --proxy-headers: za Caddy adres klienta i schemat (https) bierzemy z X-Forwarded-*;
# port 8000 nie jest wystawiony na zewnątrz, więc zapytania przychodzą tylko od proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
