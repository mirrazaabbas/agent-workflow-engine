FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk upgrade --no-cache

WORKDIR /app
COPY engine.py ./engine.py

USER nobody
CMD ["python", "engine.py"]
