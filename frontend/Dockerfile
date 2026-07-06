# Frontend production image: build tĩnh (Vite) → phục vụ + reverse-proxy /api bằng nginx.
# syntax=docker/dockerfile:1

# ---- Stage 1: build ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Production same-origin: nginx proxy /api → backend, nên client gọi ĐƯỜNG DẪN TƯƠNG ĐỐI.
# Để trống VITE_API_BASE_URL ⇒ BASE_URL rỗng ⇒ fetch("/api/...").
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ---- Stage 2: serve ----
FROM nginx:1.27-alpine AS runtime
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
