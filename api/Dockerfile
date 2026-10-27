FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
ARG BUILD_ID=2026-10-27-jpy-fix
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:17-jre
RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /build/target/forexbot-api-1.0.0.jar app.jar
ENV JAVA_OPTS="-Xms128m -Xmx512m -Duser.timezone=UTC"
EXPOSE 8080
# Liveness only — overall /actuator/health can be DOWN (e.g. DB blip) without trapping the container in "starting".
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=6 \
  CMD wget -qO- http://127.0.0.1:8080/actuator/health/liveness || exit 1
ENTRYPOINT ["sh","-c","java $JAVA_OPTS -jar app.jar"]
