# Flutter web app. API_URL is the live Java API the browser will call.
FROM ghcr.io/cirruslabs/flutter:stable AS build
WORKDIR /app
COPY pubspec.yaml pubspec.lock* analysis_options.yaml ./
RUN flutter create --project-name waya_fx_bot --org com.wayaspot --platforms=web .
COPY pubspec.yaml pubspec.lock* analysis_options.yaml ./
COPY assets ./assets
COPY lib ./lib
COPY web ./web
COPY test ./test
RUN flutter pub get
ARG API_URL=http://145.241.187.174:8088
ARG BUILD_ID=2026-10-27-jpy-fix
RUN flutter build web --release --dart-define=API_URL=${API_URL} --dart-define=BUILD_ID=${BUILD_ID}

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build/web /usr/share/nginx/html
EXPOSE 80
