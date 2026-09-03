FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY infra/images/backtest/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /app/requirements.txt

COPY packages/backtest/backtest /app/backtest
COPY packages/backtest/ta.py /app/ta.py
COPY packages/data/data /app/data
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk

ENV PYTHONPATH=/app

CMD ["python", "-m", "backtest.runner"]
