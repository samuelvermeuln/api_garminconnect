FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY garminconnect ./garminconnect
COPY garmin_api ./garmin_api
COPY garmin_mcp ./garmin_mcp

RUN pip install --no-cache-dir -e ".[api,mcp]"

EXPOSE 8000
EXPOSE 8010

CMD ["uvicorn", "garmin_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
