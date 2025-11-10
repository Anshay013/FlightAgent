package com.flightMcp.AgentMCP.service;

import com.flightMcp.AgentMCP.adapter.FlightAdapter;
import com.flightMcp.AgentMCP.model.FlightQuery;
import com.flightMcp.AgentMCP.model.FlightResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

@Slf4j
@Service
public class FlightService {

    private final List<FlightAdapter> adapters;

    public FlightService(List<FlightAdapter> adapters) {
        this.adapters = adapters;
    }

    @Cacheable(value = "flightResults",
            key = "T(com.flightMcp.AgentMCP.service.FlightService).cacheKey(#query)")
    public List<FlightResult> searchFlights(FlightQuery query) {
        log.info("✈️ Searching flights for {} -> {} ({})",
                query.getOrigin(), query.getDestination(), query.getIntent());

        if (adapters.isEmpty()) {
            log.warn("⚠️ No adapters registered!");
            return List.of();
        }

        // Run only AmadeusAdapter (no need for multithreading)
        List<FlightResult> allResults = new ArrayList<>();
        for (FlightAdapter adapter : adapters) {
            if (adapter.supports(query)) {
                try {
                    log.info("🔹 Using adapter [{}]", adapter.getProviderName());
                    allResults.addAll(adapter.search(query));
                } catch (Exception e) {
                    log.error("❌ Error calling [{}]: {}", adapter.getProviderName(), e.getMessage());
                }
            }
        }

        log.info("🟢 Retrieved {} results from Amadeus", allResults.size());

        applyFilters(query, allResults);
        applyIntentLogic(query, allResults);

        if (query.getLimit() != null && query.getLimit() > 0 && allResults.size() > query.getLimit()) {
            allResults = allResults.subList(0, query.getLimit());
        }

        log.info("✅ Final {} results ready to send", allResults.size());
        return allResults;
    }

    private void applyFilters(FlightQuery query, List<FlightResult> results) {
        if (query.getMinPrice() != null)
            results.removeIf(r -> r.getPrice() < query.getMinPrice());
        if (query.getMaxPrice() != null)
            results.removeIf(r -> r.getPrice() > query.getMaxPrice());
        if (query.getCurrency() != null)
            results.removeIf(r -> r.getCurrency() == null ||
                    !r.getCurrency().equalsIgnoreCase(query.getCurrency()));
    }

    private void applyIntentLogic(FlightQuery query, List<FlightResult> results) {
        if (query.getIntent() == null) return;

        switch (query.getIntent().toLowerCase()) {
            case "cheapest":
            case "price_range":
                results.sort(Comparator.comparingDouble(FlightResult::getPrice));
                break;

            case "earliest":
                results.sort(Comparator.comparing(FlightResult::getDepartureTime));
                break;

            case "direct":
                results.removeIf(r -> r.getStops() > 0);
                break;

            default:
                results.sort(Comparator.comparingDouble(FlightResult::getPrice));
        }
    }

    public static String cacheKey(FlightQuery q) {
        return String.join("_",
                safe(q.getOrigin()), safe(q.getDestination()),
                String.valueOf(q.getPassengers()),
                safe(q.getCabinClass()), safe(q.getCurrency()),
                String.valueOf(q.getIntent()),
                String.valueOf(q.getMinPrice()), String.valueOf(q.getMaxPrice())
        );
    }

    private static String safe(String s) {
        return s == null ? "NA" : s.replaceAll("\\s+", "").toUpperCase();
    }
}