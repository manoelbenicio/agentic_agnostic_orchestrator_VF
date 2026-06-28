FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && groupadd --system aop \
    && useradd --system --gid aop --home /app --shell /usr/sbin/nologin aop

COPY pyproject.toml ./
COPY ai_runtime ./ai_runtime
COPY app ./app
COPY core ./core
COPY coupling ./coupling
COPY executors ./executors
COPY finops ./finops
COPY inbox_api ./inbox_api
COPY issues_api ./issues_api
COPY llm_gateway ./llm_gateway
COPY messaging ./messaging
COPY orchestrator ./orchestrator
COPY projects_api ./projects_api
COPY rag_pipeline ./rag_pipeline
COPY registry ./registry
COPY rotation ./rotation
COPY scheduler ./scheduler
COPY seats ./seats
COPY seats_api ./seats_api
COPY sessions_api ./sessions_api
COPY settings_api ./settings_api
COPY squad_api ./squad_api
COPY tasks_api ./tasks_api
COPY topology ./topology
COPY tracing ./tracing

RUN pip install . \
    && python -m compileall -q . \
    && rm -rf /root/.cache /tmp/* ./*.egg-info

USER aop
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
