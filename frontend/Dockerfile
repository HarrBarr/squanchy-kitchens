# ---- deps: shared by the dev server, the tests and the production build ----
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---- dev: `ng serve` with hot reload, and the image the frontend tests run in ----
FROM deps AS dev
COPY . .
EXPOSE 4200
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4200", "--proxy-config", "proxy.conf.json", "--poll", "1000"]

# ---- build ----
FROM deps AS build
COPY . .
RUN npx ng build --configuration production

# ---- runtime: nginx serves the SPA and proxies /api to the api service ----
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
EXPOSE 80
