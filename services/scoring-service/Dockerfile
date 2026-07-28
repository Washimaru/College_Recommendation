FROM python:3.11-slim
WORKDIR /app
# app/ must be copied BEFORE the install: pyproject declares
# [tool.setuptools] packages = ["app"], so the package dir has to exist.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8001/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
