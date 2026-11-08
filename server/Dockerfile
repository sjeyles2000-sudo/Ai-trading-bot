FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TRADING_MODE=paper PAPER_STATE_DIR=/data
WORKDIR /app
# Railway attached volumes are root-owned. A tiny root bootstrap adjusts
# /data ownership then drops privilege for the actual Python worker.
RUN apt-get update && apt-get install --no-install-recommends -y gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system paper && useradd --system --gid paper --home-dir /app paper \
    && mkdir -p /data /app/server
COPY bot.py demo_runner.py paper_dashboard.py /app/
COPY server/paper_worker.py /app/server/paper_worker.py
COPY server/entrypoint.sh /app/server/entrypoint.sh
RUN chmod 0755 /app/server/entrypoint.sh && chown -R paper:paper /app /data
# Only the bootstrap runs as root; the worker itself runs as 'paper'.
ENTRYPOINT ["/app/server/entrypoint.sh"]
CMD ["python","server/paper_worker.py"]
