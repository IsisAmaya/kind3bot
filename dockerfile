FROM ubuntu:22.04

WORKDIR /app
COPY . /app

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Bogota

RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    pkg-config \
    python3-pip \
    qt6-base-dev \
    qmake6 \
    libxml2-dev \
    calibre \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
RUN pip install -r requirements.txt

RUN pip install --no-binary lxml lxml


CMD ["python3", "bot.py"]

