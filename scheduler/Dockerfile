FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

# scrapy + crawlers require network; no extra system deps needed for scheduler alone
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

RUN useradd -m appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

VOLUME ["/data"]

CMD ["python", "main.py"]
