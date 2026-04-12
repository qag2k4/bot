FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus0 \
    libffi-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh

ENV PYTHONUNBUFFERED=1

CMD ["./start.sh"]