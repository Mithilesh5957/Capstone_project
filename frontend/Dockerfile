# Build stage: assumes standard CRA layout (package.json + src/App.js + Tailwind)
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
# R7: deterministic install from the committed lockfile (fail fast on drift).
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000/api/v1
ARG REACT_APP_API_URL=http://localhost:8000
# Optional white-label branding shown on the login screen. Empty (default)
# keeps the built-in "KL University" fallback in src/screens/LoginScreen.jsx;
# set the build arg to rebrand WITHOUT editing source (requires rebuild).
ARG REACT_APP_ORG_NAME
ENV VITE_API_URL=$VITE_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_ORG_NAME=$REACT_APP_ORG_NAME
RUN npm run build

# Serve stage
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
