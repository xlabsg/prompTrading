FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install PostgreSQL client for migrations
# FFmpeg for YouTube audio processing (DISABLED - YouTube import temporarily disabled)
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*
    # ffmpeg && \
    # rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY services/api/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy and install OKX SDK package (keep isolated for better cache reuse)
COPY packages/okx_sdk /tmp/okx_sdk
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/okx_sdk && rm -rf /tmp/okx_sdk

# Copy and install Risk Engine package (trading engine internal SDK)
COPY packages/risk_engine /tmp/risk_engine
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/risk_engine && rm -rf /tmp/risk_engine

# Copy and install Code Editor package (AI code editing with fuzzy matching)
COPY packages/code_editor /tmp/code_editor
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/code_editor && rm -rf /tmp/code_editor

# Copy agent package (strategy refinement prompts and logic)
COPY packages/agent/agent /app/agent

# Copy control plane package
COPY packages/control_plane/control_plane /app/control_plane

# Copy tradingview_scraper package (for strategy import)
COPY packages/tradingview_scraper /tmp/tradingview_scraper
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/tradingview_scraper && rm -rf /tmp/tradingview_scraper

# Copy trending_scraper package (for TradingView trending strategies)
COPY packages/trending_scraper /tmp/trending_scraper
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/trending_scraper && rm -rf /tmp/trending_scraper

# Copy youtube_processor package (DISABLED - YouTube import temporarily disabled)
# COPY packages/youtube_processor /tmp/youtube_processor
# RUN --mount=type=cache,target=/root/.cache/pip \
#     pip install --no-cache-dir /tmp/youtube_processor && rm -rf /tmp/youtube_processor
# Note: This package includes large dependencies:
#   - openai-whisper (~200MB)
#   - torch (~800MB)
#   - torchaudio (~200MB)

# Copy live trading SDK (for strategy authors)
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk

# Copy backtest utilities (strategy_spec loader, etc.)
COPY packages/backtest/backtest /app/backtest

# Copy data utilities (for fetching market data)
COPY packages/data/data /app/data

# Copy API code
COPY services/api/app /app/app

# Copy tests (for integration testing)
COPY services/api/tests /app/tests
COPY services/api/pytest.ini /app/pytest.ini

# Copy scripts
COPY services/api/scripts /app/services/api/scripts

# Copy migrations
COPY services/api/migrations /app/services/api/migrations

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
