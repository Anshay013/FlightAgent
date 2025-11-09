package com.flightMcp.AgentMCP.service;


import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Slf4j
@Component
public class TokenCache {

    private static final String CACHE_NAME = "amadeusToken";

    @Cacheable(value = CACHE_NAME, key = "'access_token'")
    public String getAccessToken() {
        // This method will only run if cache miss occurs
        log.debug("Cache miss: Amadeus access token not found");
        return null;
    }

    @Cacheable(value = CACHE_NAME, key = "'expiry_time'")
    public Instant getExpiryTime() {
        log.debug("Cache miss: Token expiry not found");
        return null;
    }

    @CachePut(value = CACHE_NAME, key = "'access_token'")
    public String storeAccessToken(String token) {
        log.info("🔐 Stored Amadeus token in Redis via @CachePut");
        return token;
    }

    @CachePut(value = CACHE_NAME, key = "'expiry_time'")
    public Instant storeExpiryTime(Instant expiry) {
        log.info("⏱️ Stored token expiry time: {}", expiry);
        return expiry;
    }

    @CacheEvict(value = CACHE_NAME, allEntries = true)
    public void evictAll() {
        log.info("🧹 Evicted Amadeus token cache (manual refresh)");
    }

    public boolean isValid() {
        String token = getAccessToken();
        Instant expiry = getExpiryTime();
        return token != null && expiry != null && Instant.now().isBefore(expiry);
    }
}
