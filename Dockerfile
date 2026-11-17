# Derived from protected GitHub main by scripts/build_command_center_space.py.
# Fixed OCI index digest for official current Python 3.12 slim Bookworm (2026-11-17).
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SZL_COMMAND_CENTER_MODE=public_preview
WORKDIR /app
COPY requirements-space.txt /app/requirements-space.txt
RUN python -m pip install --disable-pip-version-check --no-cache-dir -r requirements-space.txt && python -m pip check
RUN groupadd --system --gid 10001 szl && useradd --system --uid 10001 --gid szl --home-dir /app --shell /usr/sbin/nologin szl
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY Dockerfile /app/Dockerfile
COPY source_manifest.json /app/source_manifest.json
RUN chown -R szl:szl /app
USER 10001:10001
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:7860/api/health', timeout=3).status == 200"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
