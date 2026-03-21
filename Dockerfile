
FROM python:3.12.13-slim-trixie

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY bot.py .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]