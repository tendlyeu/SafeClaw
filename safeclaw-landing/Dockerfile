FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Coolify passes SOURCE_COMMIT automatically; falls back to build date
ARG SOURCE_COMMIT=unknown
RUN echo "${SOURCE_COMMIT} $(date -u '+%Y-%m-%d %H:%M:%S UTC')" > .version

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
