FROM codercom/code-server:4.108.1

USER root

# Minimal Python toolchain so users can run simple scripts in the dev sandbox.
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

USER coder

EXPOSE 8080

# Traefik forward-auth protects this; disable built-in auth for MVP.
CMD ["code-server", "--bind-addr", "0.0.0.0:8080", "--auth", "none", "/workspaces"]
