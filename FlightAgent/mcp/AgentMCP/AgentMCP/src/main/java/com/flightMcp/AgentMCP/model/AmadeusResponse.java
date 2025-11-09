package com.flightMcp.AgentMCP.model;

import lombok.Data;
import java.util.List;

@Data
public class AmadeusResponse {
    private List<Offer> data;

    @Data
    public static class Offer {
        private String id;
        private Price price;
        private List<Itinerary> itineraries;
    }

    @Data
    public static class Price {
        private String currency;
        private String total;
    }

    @Data
    public static class Itinerary {
        private List<Segment> segments;
    }

    @Data
    public static class Segment {
        private Location departure;
        private Location arrival;
        private String carrierCode;
        private String number;
    }

    @Data
    public static class Location {
        private String iataCode;
        private String at;
    }
}