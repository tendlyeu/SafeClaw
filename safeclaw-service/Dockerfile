FROM python:3.12-slim

WORKDIR /app

# Create non-root user before installing packages (R3-51)
RUN useradd -m -r safeclaw && \
    mkdir -p /home/safeclaw/.safeclaw/audit && \
    chown -R safeclaw:safeclaw /home/safeclaw/.safeclaw

COPY pyproject.toml .
COPY safeclaw/ safeclaw/
RUN pip install --no-cache-dir .

USER safeclaw

EXPOSE 8420

CMD ["uvicorn", "safeclaw.main:app", "--host", "0.0.0.0", "--port", "8420"]
