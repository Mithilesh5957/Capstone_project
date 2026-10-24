# Build stage: assumes standard CRA layout (package.json + src/App.js + Tailwind)
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_URL=http://localhost:8000/api/v1
ARG REACT_APP_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

# Serve stage
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
