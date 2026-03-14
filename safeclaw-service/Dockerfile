FROM python:3.12-slim

WORKDIR /app

# Create non-root user before installing packages (R3-51)
RUN useradd -m -r safeclaw && \
    mkdir -p /home/safeclaw/.safeclaw/audit && \
    chown -R safeclaw:safeclaw /home/safeclaw/.safeclaw

COPY pyproject.toml .
COPY requirement*.lock ./
COPY safeclaw/ safeclaw/
RUN if [ -f requirements.lock ]; then \
        pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .; \
    else \
        pip install --no-cache-dir .; \
    fi && \
    chown -R safeclaw:safeclaw /app

USER safeclaw

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/v1/health')" || exit 1

CMD ["uvicorn", "safeclaw.main:app", "--host", "0.0.0.0", "--port", "8420"]
