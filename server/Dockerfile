FROM python:3.12-slim

# git is the only system dependency
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py git_ops.py ./

# /data/repo  — mounted volume; git working tree lives here
RUN mkdir -p /data/repo

EXPOSE 8080

CMD ["python", "app.py"]
