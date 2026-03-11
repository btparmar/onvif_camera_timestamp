FROM python:3.12-slim

WORKDIR /app

RUN pip install requests

COPY onvif_timestamp_monitor.py .

ENTRYPOINT ["python", "onvif_timestamp_monitor.py"]
