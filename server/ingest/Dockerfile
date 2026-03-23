FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

COPY server/ingest/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server/ingest /app/server/ingest
RUN chown -R app:app /app

WORKDIR /app/server/ingest
USER app
CMD ["python", "run.py"]
