FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# database, model, and downloads live on the volume
ENV POKEPRICE_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# set POKEPRICE_PASSWORD to require login; drop --auto-fetch for manual control.
# Honors the platform's $PORT (Railway/Render/Heroku) and defaults to 8000.
CMD ["sh", "-c", "pokeprice serve --host 0.0.0.0 --port ${PORT:-8000} --auto-fetch daily"]
