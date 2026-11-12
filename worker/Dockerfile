# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG PRUSA_DEBIAN_VERSION=2.5.0+dfsg-4
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::http::Proxy="$HTTP_PROXY" -o Acquire::https::Proxy="$HTTPS_PROXY" -o Acquire::https::CaInfo=/run/secrets/proxy_ca update -qq \
    && apt-get -o Acquire::http::Proxy="$HTTP_PROXY" -o Acquire::https::Proxy="$HTTPS_PROXY" -o Acquire::https::CaInfo=/run/secrets/proxy_ca install --no-install-recommends -y prusa-slicer="$PRUSA_DEBIAN_VERSION" \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home worker
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --chown=0:0 worker /opt/worker
COPY --chown=0:0 backend/app/analysis/profile_config.py /opt/worker/profiles.py
COPY --chown=0:0 backend/app/intake/validation.py /opt/worker/structural.py
RUN dpkg-query -W > /opt/worker/debian-packages.txt && chmod -R a+rX /opt/worker
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "HOME=/work/home", "XDG_CONFIG_HOME=/work/home", "PYTHONDONTWRITEBYTECODE=1", "python", "-I", "-B", "/opt/worker/main.py"]
