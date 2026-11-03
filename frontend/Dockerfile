FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# The cache mount keeps npm's downloads between builds.
RUN --mount=type=cache,target=/root/.npm npm ci

# For tests, lint and typecheck: the sources, without a production build (they do not need one).
FROM deps AS test
COPY . .

FROM deps AS build
COPY . .
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
