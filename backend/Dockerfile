FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN groupadd --gid 10001 spikelens \
    && useradd --uid 10001 --gid spikelens --no-create-home spikelens \
    && mkdir -p /data/uploads \
    && chown -R spikelens:spikelens /app /data
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY --chown=spikelens:spikelens app ./app
COPY --chown=spikelens:spikelens alembic ./alembic
COPY --chown=spikelens:spikelens tests ./tests
COPY --chown=spikelens:spikelens alembic.ini pyproject.toml ./

USER spikelens
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
