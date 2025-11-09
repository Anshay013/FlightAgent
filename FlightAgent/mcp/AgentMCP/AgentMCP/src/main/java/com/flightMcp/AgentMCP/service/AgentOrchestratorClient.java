package com.flightMcp.AgentMCP.service;

import com.flightMcp.AgentMCP.model.FlightQuery;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.util.Map;

@Service
public class AgentOrchestratorClient {
    private final WebClient webClient;

    public AgentOrchestratorClient(@Value("${orchestrator.url:http://localhost:8081}") String url) {
        this.webClient = WebClient.builder().baseUrl(url).build();
    }

    public Map<String,Object> queryLangChain(FlightQuery query) {
        return webClient.post().uri("/agent/search")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(query)
                .retrieve().bodyToMono(Map.class).block();
    }

    public Flux<ServerSentEvent<String>> streamLangChain(FlightQuery query, String sessionId) {
        return webClient.post()
                .uri(uri -> uri.path("/agent/search/stream").queryParam("session_id", sessionId).build())
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(query)
                .retrieve()
                .bodyToFlux(String.class)
                .map(data -> ServerSentEvent.builder(data).build());
    }
}
