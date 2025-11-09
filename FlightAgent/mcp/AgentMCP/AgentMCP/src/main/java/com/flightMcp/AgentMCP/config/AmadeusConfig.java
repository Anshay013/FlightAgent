package com.flightMcp.AgentMCP.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Getter
@Setter
@Configuration
@ConfigurationProperties(prefix = "provider.amadeus")
public class AmadeusConfig {
    private String baseUrl;
    private String tokenUrl = "https://test.api.amadeus.com/v1/security/oauth2/token";
    private String clientId;
    private String clientSecret;
}
