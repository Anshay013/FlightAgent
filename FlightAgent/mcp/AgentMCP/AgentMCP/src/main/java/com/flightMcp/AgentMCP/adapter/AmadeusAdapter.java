package com.flightMcp.AgentMCP.adapter;

import com.flightMcp.AgentMCP.config.AmadeusConfig;
import com.flightMcp.AgentMCP.exception.ExternalApiException;
import com.flightMcp.AgentMCP.model.AmadeusResponse;
import com.flightMcp.AgentMCP.model.FlightQuery;
import com.flightMcp.AgentMCP.model.FlightResult;
import com.flightMcp.AgentMCP.service.TokenCache;
import io.github.resilience4j.retry.annotation.Retry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class AmadeusAdapter implements FlightAdapter {

    private final WebClient amadeusWebClient;
    private final AmadeusConfig config;
    private final TokenCache tokenCache;

    @Override
    public String getProviderName() {
        return "Amadeus";
    }

    @Override
    public boolean supports(FlightQuery query) {
        return true;
    }

    @Override
    @Retry(name = "amadeusAdapter", fallbackMethod = "fallbackSearch")
    public List<FlightResult> search(FlightQuery query) {
        log.info("🔹 Searching flights via Amadeus API for {} → {}", query.getOrigin(), query.getDestination());

        try {
            String token = ensureToken();
            String url = String.format(
                    "%s/flight-offers?originLocationCode=%s&destinationLocationCode=%s&departureDate=%s&adults=%d&currencyCode=%s&max=%d",
                    config.getBaseUrl(),
                    query.getOrigin(),
                    query.getDestination(),
                    query.getDepartDate(),
                    query.getPassengers(),
                    query.getCurrency(),
                    query.getLimit() == null ? 10 : query.getLimit()
            );

            AmadeusResponse response = amadeusWebClient.get()
                    .uri(url)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, r -> {
                        log.error("❌ Amadeus API error: {}", r.statusCode());
                        return r.bodyToMono(String.class)
                                .flatMap(body -> Mono.error(new RuntimeException("Amadeus error: " + body)));
                    })
                    .bodyToMono(AmadeusResponse.class)
                    .block();

            return mapResults(response);

        } catch (Exception e) {
            log.error("❌ Exception during Amadeus search: {}", e.getMessage());
            return List.of();
        }
    }

    private String ensureToken() {
        if (tokenCache.isValid()) {
            return tokenCache.getAccessToken();
        }

        log.info("🔑 Fetching new Amadeus access token...");

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "client_credentials");
        form.add("client_id", config.getClientId());
        form.add("client_secret", config.getClientSecret());

        var tokenResponse = amadeusWebClient.post()
                .uri(config.getTokenUrl())
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_FORM_URLENCODED_VALUE)
                .body(BodyInserters.fromFormData(form))
                .retrieve()
                .bodyToMono(TokenResponse.class)
                .block();

        Instant expiryTime = Instant.now().plusSeconds(tokenResponse.expires_in - 60);
        tokenCache.storeAccessToken(tokenResponse.access_token);
        tokenCache.storeExpiryTime(expiryTime);

        return tokenResponse.access_token;
    }

    private List<FlightResult> mapResults(AmadeusResponse resp) {
        List<FlightResult> list = new ArrayList<>();
        if (resp == null || resp.getData() == null) return list;

        for (var offer : resp.getData()) {
            try {
                var itinerary = offer.getItineraries().get(0);
                var segment = itinerary.getSegments().get(0);

                FlightResult fr = new FlightResult();
                fr.setProvider(getProviderName());
                fr.setProviderFlightId(offer.getId());
                fr.setOrigin(segment.getDeparture().getIataCode());
                fr.setDestination(segment.getArrival().getIataCode());
                fr.setDepartureTime(segment.getDeparture().getAt());
                fr.setArrivalTime(segment.getArrival().getAt());
                fr.setAirline(segment.getCarrierCode());
                fr.setStops(itinerary.getSegments().size() - 1);
                fr.setPrice(Double.parseDouble(offer.getPrice().getTotal()));
                fr.setCurrency(offer.getPrice().getCurrency());

                list.add(fr);
            } catch (Exception e) {
                log.warn("⚠️ Error parsing offer: {}", e.getMessage());
            }
        }

        log.info("✅ Parsed {} flight offers from Amadeus", list.size());
        return list;
    }

    private List<FlightResult> fallbackSearch(FlightQuery query, Exception ex) {
        log.error("⚠️ Amadeus fallback triggered due to: {}", ex.getMessage());
        return List.of();
    }

    // Internal DTO
    private record TokenResponse(String access_token, int expires_in) {}
}