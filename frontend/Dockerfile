# Build stage
FROM node:20-alpine as build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application. Версия приходит аргументом: корневой VERSION лежит вне
# контекста сборки (frontend/), и без него бандл показывал бы 'dev'.
ARG APP_VERSION=dev
RUN APP_VERSION="${APP_VERSION}" npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
