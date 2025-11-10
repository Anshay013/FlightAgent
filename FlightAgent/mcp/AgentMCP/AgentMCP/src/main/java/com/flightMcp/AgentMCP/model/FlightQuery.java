package com.flightMcp.AgentMCP.model;

import lombok.Getter;
import lombok.Setter;

import java.time.LocalDate;

@Getter
@Setter

public class FlightQuery {
    private String origin;
    private String destination;
    private LocalDate departDate;
    private LocalDate returnDate;
    private Integer passengers = 1;
    private String cabinClass = "Economy";
    private String currency = "INR";
    private Integer limit = 10;
    private Double minPrice;
    private Double maxPrice;
    private String intent = "cheapest";
    private String region; // optional
    private String airline;

}
