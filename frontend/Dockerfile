FROM node:22-alpine AS build
WORKDIR /app
RUN npm install --global pnpm@11.19.0
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
ARG NEXT_PUBLIC_WS_ORIGIN
ENV NEXT_PUBLIC_WS_ORIGIN=$NEXT_PUBLIC_WS_ORIGIN
RUN pnpm build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
