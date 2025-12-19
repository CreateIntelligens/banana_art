FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# We mount the code via volumes in docker-compose, so no need to COPY everything here for dev
