FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate version info from git at build time (Coolify clones the repo)
RUN git log -1 --format='%h %ci' > .version 2>/dev/null || echo "unknown" > .version

RUN groupadd -r safeclaw && useradd -m -r -g safeclaw safeclaw

# Make app dir writable by safeclaw (FastHTML writes .sesskey at runtime)
# and tighten data directory for SQLite
RUN mkdir -p /home/safeclaw/.safeclaw-landing && \
    chown safeclaw:safeclaw /home/safeclaw/.safeclaw-landing && \
    chmod 770 /home/safeclaw/.safeclaw-landing && \
    chown -R safeclaw:safeclaw /app

USER safeclaw

EXPOSE 5002

CMD ["python", "main.py"]
