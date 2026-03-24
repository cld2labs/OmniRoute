FROM node:22-alpine

WORKDIR /app

RUN addgroup -S app && adduser -S app -G app

COPY client/package.json /app/package.json
RUN npm install

COPY client /app
RUN chown -R app:app /app

USER app
EXPOSE 5173
CMD ["npm", "run", "dev"]
