FROM python:3.11.5-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# build-essential: gcc, g++, make 
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel Cython

RUN pip install --no-cache-dir poetry

RUN poetry config virtualenvs.create false

# .dockerignore 
COPY . .

RUN poetry install --no-interaction --no-ansi
