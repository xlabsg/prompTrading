FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# install runtime tooling and git for version control
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tar unzip git build-essential \
    && rm -rf /var/lib/apt/lists/*

# install python dependencies
COPY infra/images/agent/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r /app/requirements.txt

# copy and install code_editor for patch application
COPY packages/code_editor /tmp/code_editor
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/code_editor && rm -rf /tmp/code_editor

COPY packages/agent/agent /app/agent
COPY packages/backtest/backtest /app/backtest
COPY packages/data/data /app/data
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk

ENV PYTHONPATH=/app

CMD ["python", "-m", "agent.runner_v2"]
