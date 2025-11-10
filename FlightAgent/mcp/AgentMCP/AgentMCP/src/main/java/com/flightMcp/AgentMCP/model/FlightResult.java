package com.flightMcp.AgentMCP.model;


import lombok.Getter;
import lombok.Setter;

@Getter
@Setter


public class FlightResult {
    private String provider;
    private String providerFlightId;
    private String origin;
    private String destination;
    private String airline;
    private String departureTime;
    private String arrivalTime;
    private int stops;
    private double price;
    private String currency;
    private String cabinClass = "Economy";
}

