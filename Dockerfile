FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS builder
RUN apk add --no-cache build-base
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir /build/dist/*.whl \
        "predictor-core @ https://github.com/leonardosovienski/core-predictor/releases/download/v2.3.0/predictor_core-2.3.0-py3-none-any.whl" \
        "predictor-ops @ https://github.com/leonardosovienski/predictor-ops/releases/download/v3.1.0/predictor_ops-3.1.0-py3-none-any.whl" \
    && /opt/venv/bin/python -m pip uninstall --yes pip \
    && rm -rf /root/.cache /tmp/*

FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN addgroup -S app && adduser -S -G app -h /app app \
    && python -m pip uninstall --yes pip \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 \
        /usr/bin/wget /sbin/apk \
    && rm -rf /root/.cache /tmp/* /var/cache/apk/*
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY config.yaml ./config.yaml
COPY data/teams_cs.json ./data/teams_cs.json
USER app
VOLUME ["/var/lib/cs-predictor"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["cs-predictor", "health"]
ENTRYPOINT ["cs-predictor"]
CMD ["health"]
