# === Stage 1: Build ===
FROM maven:3.9.8-eclipse-temurin-23 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn -DskipTests clean package

# === Stage 2: Run ===
FROM eclipse-temurin:23-jdk
WORKDIR /app
COPY --from=build /app/target/flight-agent-mcp-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
