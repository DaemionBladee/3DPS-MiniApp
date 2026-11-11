# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV STORAGE_ROOT=/srv/private_uploads
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/backend:/srv
WORKDIR /srv/backend
COPY backend/requirements.txt ./requirements.txt
# The optional build secret supplies managed-cloud CA trust without putting it
# in any image layer. Ordinary local builders use the image's normal CA bundle.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir --require-hashes -r requirements.txt; \
    else \
      pip install --no-cache-dir --require-hashes -r requirements.txt; \
    fi
RUN useradd --uid 10001 --create-home app && mkdir -p /srv/private_uploads && chown app:app /srv/private_uploads && chmod 700 /srv/private_uploads
COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/alembic.ini ./alembic.ini
COPY --chown=app:app backend/scripts/cleanup_uploads.py ./scripts/cleanup_uploads.py
COPY --chown=app:app telegram_bot /srv/telegram_bot
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
