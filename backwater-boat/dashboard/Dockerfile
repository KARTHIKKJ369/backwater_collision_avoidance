FROM node:20-alpine

WORKDIR /app
COPY dashboard/package.json /app/package.json
RUN npm install
COPY dashboard /app

EXPOSE 5173
CMD ["npm", "run", "dev"]
