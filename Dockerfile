FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV DATA_DIR=/data

RUN mkdir -p /data && chown -R app:app /data /app

USER app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
