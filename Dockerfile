FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY app /app/app
COPY static /app/static
RUN pip install --no-cache-dir . && mkdir -p /data && useradd -m -u 10001 incident && chown incident:incident /data
USER incident
ENV INCIDENT_DB_PATH=/data/incidents.db
EXPOSE 8000
# Bind the published Docker port to 127.0.0.1 on your host; this demo has NO authentication.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
