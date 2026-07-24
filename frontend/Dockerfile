# Frontend — build the SPA with Node, serve it with nginx.

# ---- build stage ----------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first (cached until the lockfile changes).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- serve stage ----------------------------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
