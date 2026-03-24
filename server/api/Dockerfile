FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

COPY server/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server/api /app/server/api
COPY server/agents /app/server/agents
COPY server/db/migrations /app/server/db/migrations
RUN chown -R app:app /app

ENV PYTHONPATH=/app/server
USER app
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
