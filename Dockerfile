FROM python:3.12-slim

RUN useradd -m -u 1000 app
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[server]"

COPY briefs ./briefs
RUN mkdir -p projects && chown -R app:app /app
USER app

ENV PLANFORGE_WORKSPACE=/app/projects \
    PORT=7860 \
    PYTHONUNBUFFERED=1
EXPOSE 7860

# --allow-public لازم على منصّة تُنفق المنفذ، والمصادقة تُفرض بـPLANFORGE_TOKEN
CMD ["planforge", "serve", "--host", "0.0.0.0", "--allow-public"]
