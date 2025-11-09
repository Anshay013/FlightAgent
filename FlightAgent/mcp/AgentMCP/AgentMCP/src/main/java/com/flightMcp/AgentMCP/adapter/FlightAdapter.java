package com.flightMcp.AgentMCP.adapter;

import com.flightMcp.AgentMCP.model.FlightQuery;
import com.flightMcp.AgentMCP.model.FlightResult;

import java.util.List;

public interface FlightAdapter {
    String getProviderName();
    boolean supports(FlightQuery query);
    List<FlightResult> search(FlightQuery query);
}