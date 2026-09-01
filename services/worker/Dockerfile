FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/worker/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy trending_scraper package (for TradingView trending strategies)
COPY packages/trending_scraper /tmp/trending_scraper
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/trending_scraper && rm -rf /tmp/trending_scraper

# Copy tradingview_scraper package (for scraping individual TradingView scripts)
COPY packages/tradingview_scraper /tmp/tradingview_scraper
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/tradingview_scraper && rm -rf /tmp/tradingview_scraper

COPY packages/control_plane/control_plane /app/control_plane
COPY packages/backtest/backtest /app/backtest
COPY packages/code_editor /app/code_editor
COPY packages/data/data /app/data
COPY packages/agent/agent /app/agent
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk
COPY packages/strategy_templates/strategy_templates /app/strategy_templates
COPY services/worker/worker /app/worker

ENV PYTHONPATH=/app

CMD ["python", "-m", "worker.main"]
