# Use a Python 3.9.6 Alpine base image
FROM python:3.9.6-alpine3.14

# Set the working directory
WORKDIR /app

# Copy all files from the current directory to the container's /app directory
COPY . .

# Add community repository for imagemagick and imagemagick-dev
RUN echo "http://dl-cdn.alpinelinux.org/alpine/v3.14/community" >> /etc/apk/repositories && \
    apk update

# Install necessary dependencies
RUN apk add --no-cache \
    gcc \
    libffi-dev \
    musl-dev \
    ffmpeg \
    aria2 \
    make \
    g++ \
    cmake \
    fontconfig \
    ttf-dejavu \
    wget \
    unzip

# Install imagemagick and imagemagick-dev
RUN apk add --no-cache imagemagick imagemagick-dev

# Install Bento4
RUN wget -q https://github.com/axiomatic-systems/Bento4/archive/v1.6.0-639.zip && \
    unzip v1.6.0-639.zip && \
    cd Bento4-1.6.0-639 && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j$(nproc) && \
    cp mp4decrypt /usr/local/bin/ && \
    cd ../.. && \
    rm -rf Bento4-1.6.0-639 v1.6.0-639.zip

# Download Bebas Neue font (optional)
RUN wget -q -O /usr/share/fonts/truetype/BebasNeue-Regular.ttf https://github.com/googlefonts/bebasneue/raw/main/fonts/ttf/BebasNeue-Regular.ttf && \
    fc-cache -f

# Install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r sainibots.txt && \
    python3 -m pip install -U yt-dlp

# Set the command to run the application
CMD ["sh", "-c", "gunicorn app:app & python3 main.py"]
