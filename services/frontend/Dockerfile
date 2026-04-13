FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.25-alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: serve SPA + proxy /api/ and /s3/ to backend services.
# API_HOST build-arg defaults to "api:8000" (docker-compose service name).
# For local dev without docker-compose, set: --build-arg API_HOST=host.docker.internal:8000
ARG API_HOST=api:8000
ARG MINIO_HOST=minio:9000
RUN printf "server {\n\
    listen 3000;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
\n\
    # Proxy API requests — prevents 405 on POST /api/v1/auth/login etc.\n\
    location /api/ {\n\
        proxy_pass http://${API_HOST};\n\
        proxy_set_header Host \$host;\n\
        proxy_set_header X-Real-IP \$remote_addr;\n\
        proxy_read_timeout 120s;\n\
        client_max_body_size 50m;\n\
    }\n\
\n\
    # Proxy MinIO presigned URLs through /s3/\n\
    location /s3/ {\n\
        proxy_pass http://${MINIO_HOST}/;\n\
        proxy_set_header Host \$host;\n\
    }\n\
\n\
    # SPA fallback\n\
    location / {\n\
        try_files \$uri \$uri/ /index.html;\n\
    }\n\
}\n" > /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
