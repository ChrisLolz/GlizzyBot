FROM python:3.11.15-slim-trixie

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt .
COPY bot.py .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --force-reinstall opencv-python-headless

CMD ["python", "bot.py"]