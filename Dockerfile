FROM python:3.14-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git libusb-1.0-0 usbutils ca-certificates \
    && rm --recursive --force /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY main.py ./
COPY openstick/ openstick/
COPY loaders/ loaders/

RUN useradd --create-home openstick && chown --recursive openstick:openstick /app
USER openstick

ENTRYPOINT ["python3", "main.py"]
