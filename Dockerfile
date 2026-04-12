FROM python:3.11-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết cho Discord Voice và gTTS
# Thêm libopus-dev để hỗ trợ thư viện opus tốt hơn
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus-dev \
    libopus0 \
    libffi-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Sao chép và cài đặt requirements trước để tận dụng cache của Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn
COPY . .

# Xử lý định dạng xuống dòng (CRLF to LF) và cấp quyền thực thi cho script
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Biến môi trường quan trọng
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Lệnh chạy bot
CMD ["./start.sh"]
