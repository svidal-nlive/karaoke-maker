# syntax=docker/dockerfile:1

# Build stage
FROM node:18-alpine AS builder

# Build arguments
ARG VITE_API_BASE

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Set API base URL and build
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# Production image
FROM nginx:alpine

# Install curl for healthchecks
RUN apk add --no-cache curl

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:80/ || exit 1

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
