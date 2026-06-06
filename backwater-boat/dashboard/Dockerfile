FROM oven/bun:1

WORKDIR /app

# Install dependencies
COPY dashboard/package.json ./
COPY dashboard/bun.lock ./

RUN bun install

# Copy source
COPY dashboard/ ./

EXPOSE 5173

CMD ["bun", "run", "dev", "--host", "0.0.0.0"]