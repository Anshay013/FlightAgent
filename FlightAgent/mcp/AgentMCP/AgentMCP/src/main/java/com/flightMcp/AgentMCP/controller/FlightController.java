package com.flightMcp.AgentMCP.controller;

import com.flightMcp.AgentMCP.model.FlightQuery;
import com.flightMcp.AgentMCP.model.FlightResult;
import com.flightMcp.AgentMCP.service.AgentOrchestratorClient;
import com.flightMcp.AgentMCP.service.FlightService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

import java.util.List;

@RestController
@RequestMapping("/v1/search")
public class FlightController {

    private final FlightService flightService;
    private final AgentOrchestratorClient agentClient;

    public FlightController(FlightService flightService, AgentOrchestratorClient agentClient) {
        this.flightService = flightService;
        this.agentClient = agentClient;
    }

    @PostMapping("/flights")
    public ResponseEntity<List<FlightResult>> searchFlights(@RequestBody FlightQuery query) {
        return ResponseEntity.ok(flightService.searchFlights(query));
    }

    @PostMapping("/agent")
    public ResponseEntity<Object> searchViaAgent(@RequestBody FlightQuery query) {
        return ResponseEntity.ok(agentClient.queryLangChain(query));
    }

    @PostMapping(value = "/agent/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> streamViaAgent(@RequestBody FlightQuery query,
                                                        @RequestParam("sessionId") String sessionId) {
        return agentClient.streamLangChain(query, sessionId);
    }
}
