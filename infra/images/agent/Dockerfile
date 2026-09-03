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

COPY packages/agent/agent /app/agent
COPY packages/backtest/backtest /app/backtest
COPY packages/backtest/ta.py /app/ta.py
COPY packages/data/data /app/data
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk

ENV PYTHONPATH=/app

# Skills Tau loads from the user directory, and the provider entry it needs when
# LLM_BASE_URL points at a gateway. `tau setup` only writes files, so it is safe
# to resolve at build time.
COPY packages/agent/skills /root/.tau/skills
COPY packages/agent/skills /app/skills
RUN python -m agent.tau_config

CMD ["python", "-m", "agent.runner_v2"]
