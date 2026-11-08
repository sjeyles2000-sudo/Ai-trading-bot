FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TRADING_MODE=paper PAPER_STATE_DIR=/data
WORKDIR /app
COPY bot.py demo_runner.py paper_dashboard.py /app/
COPY server/paper_worker.py /app/server/paper_worker.py
RUN groupadd --system paper && useradd --system --gid paper --home-dir /app paper \
    && mkdir -p /data && chown -R paper:paper /data /app
USER paper
# No ports exposed, no trade/order API, no wallets or exchange keys.
CMD ["python","server/paper_worker.py"]
