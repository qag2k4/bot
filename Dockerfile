FROM python:3.11-slim

WORKDIR /app

# Thêm cấu hình cài đặt không lưu cache để giảm dung lượng và tránh lỗi build
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus-dev \
    libopus0 \
    libffi-dev \
    gcc \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Sửa lỗi dòng của Windows và cấp quyền
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["./start.sh"]
