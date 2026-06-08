FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    python3-libtorrent \
    ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh
CMD ["sh", "entrypoint.sh"]