FROM node:20-alpine

WORKDIR /app

# Copy package files first to leverage Docker layer caching
COPY dashboard/package*.json ./

# Install frontend dependencies
RUN npm install

# Copy the rest of the dashboard source code
COPY dashboard/ ./

# Expose the standard Vite development port
EXPOSE 5173

# Start the Vite server and bind to 0.0.0.0 so it is accessible from your host machine
CMD ["npm", "run", "dev", "--", "--host"]