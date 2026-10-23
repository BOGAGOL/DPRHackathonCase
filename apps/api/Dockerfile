FROM python:3.12-slim
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 API_HOST=0.0.0.0
COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --create-home --uid 10001 service
COPY apps/api /workspace/apps/api
COPY scripts /workspace/scripts
USER service
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
