FROM python:3.12-slim

WORKDIR /app
COPY engine.py ./engine.py
CMD ["python", "engine.py"]
