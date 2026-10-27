# Python trading engine. The MT5 desktop on the Windows PC dials out to
# ws://<server>:8088/mt5-bridge. The engine does not dial into the home network.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
ARG BUILD_ID=2026-10-27-jpy-fix
ENV BUILD_ID=${BUILD_ID}
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
