# The landing page alone (the /about project page at /), built static and served by Caddy with automatic HTTPS.
# Build context is frontend/ (see docker-compose.yml), so nothing outside it, the repo-root .env included, reaches the image.

# Vite 8 needs Node 20.19+ or 22.12+.
FROM node:24.11.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Where the in-page links into the app go once the app itself is deployed. Empty leaves those links out.
ARG VITE_APP_URL=""
ENV VITE_LANDING_ONLY=true VITE_APP_URL=$VITE_APP_URL
RUN npm run build

FROM caddy:2.8.4-alpine
COPY --from=build /app/dist /srv
