# Test runner image: only the dependencies. The repository is mounted at run time.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /repo
