# ============================================
# Enterprise RAG Platform — Frontend Dockerfile
# ============================================
# Development Dockerfile for Next.js with hot-reload.

FROM node:20-alpine

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY package.json package-lock.json* ./
RUN npm install

# Copy application code
COPY . .

# Expose the dev server port
EXPOSE 3000

# Run Next.js dev server
# Turbopack for faster hot-reload in development
CMD ["npm", "run", "dev"]
