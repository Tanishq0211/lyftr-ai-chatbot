FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-compile -r requirements.txt \
    && /opt/venv/bin/pip uninstall --yes pip

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
RUN mkdir /data && chown 10001:10001 /data
COPY app/ ./app/
USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --no-access-log"]
