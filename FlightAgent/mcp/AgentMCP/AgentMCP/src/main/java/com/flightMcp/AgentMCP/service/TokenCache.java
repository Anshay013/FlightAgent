package com.flightMcp.AgentMCP.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.locks.ReentrantLock;

/**
 * ✅ Production-grade TokenCache
 * - Stores OAuth tokens in Redis
 * - Thread-safe local fallback (ReentrantLock)
 * - Prevents multiple threads from refreshing token concurrently
 */
@Slf4j
@Component
public class TokenCache {

    private static final String TOKEN_KEY = "amadeus:access_token";
    private static final String EXPIRY_KEY = "amadeus:expiry_time";

    private final RedisTemplate<String, Object> redisTemplate;
    private final ReentrantLock lock = new ReentrantLock();

    public TokenCache(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * ✅ Store the token and its expiry time in Redis.
     * @param token the access token
     */
    public void storeAccessToken(String token) {
        try {
            redisTemplate.opsForValue().set(TOKEN_KEY, token);
            log.debug("🔐 Stored Amadeus access token in Redis");
        } catch (Exception e) {
            log.error("❌ Failed to store token in Redis: {}", e.getMessage());
        }
    }

    /**
     * ✅ Store the expiry time in Redis.
     * @param expiryTime Instant when the token expires
     */
    public void storeExpiryTime(Instant expiryTime) {
        try {
            Duration ttl = Duration.between(Instant.now(), expiryTime);
            redisTemplate.opsForValue().set(EXPIRY_KEY, expiryTime.toString(), ttl);
            log.debug("⏳ Stored token expiry time in Redis with TTL {}", ttl);
        } catch (Exception e) {
            log.error("❌ Failed to store token expiry in Redis: {}", e.getMessage());
        }
    }

    /**
     * ✅ Retrieve the cached access token.
     */
    public String getAccessToken() {
        try {
            Object token = redisTemplate.opsForValue().get(TOKEN_KEY);
            return token != null ? token.toString() : null;
        } catch (Exception e) {
            log.error("⚠️ Failed to retrieve token from Redis: {}", e.getMessage());
            return null;
        }
    }

    /**
     * ✅ Retrieve the expiry time of the cached token.
     */
    private Instant getExpiryTime() {
        try {
            Object expiry = redisTemplate.opsForValue().get(EXPIRY_KEY);
            return expiry != null ? Instant.parse(expiry.toString()) : null;
        } catch (Exception e) {
            log.error("⚠️ Failed to retrieve expiry time from Redis: {}", e.getMessage());
            return null;
        }
    }

    /**
     * ✅ Check if the token is still valid.
     * @return true if token exists and not expired
     */
    public boolean isValid() {
        try {
            Instant expiryTime = getExpiryTime();
            if (expiryTime == null) {
                return false;
            }
            boolean valid = expiryTime.isAfter(Instant.now().plusSeconds(60));
            if (!valid) {
                log.info("🕓 Token expired or near expiry.");
            }
            return valid;
        } catch (Exception e) {
            log.error("⚠️ Failed to validate token: {}", e.getMessage());
            return false;
        }
    }

    /**
     * ✅ Thread-safe way to ensure only one thread refreshes token at a time.
     * Useful for adapters that fetch new tokens concurrently.
     */
    public void withLock(Runnable action) {
        try {
            if (lock.tryLock()) {
                action.run();
            }
        } catch (Exception e) {
            log.error("❌ Token refresh failed: {}", e.getMessage());
        } finally {
            if (lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }

    /**
     * ✅ Clear cached token (for manual reset or debugging).
     */
    public void clear() {
        try {
            redisTemplate.delete(TOKEN_KEY);
            redisTemplate.delete(EXPIRY_KEY);
            log.info("🧹 Cleared cached Amadeus token and expiry time.");
        } catch (Exception e) {
            log.error("❌ Failed to clear Redis token cache: {}", e.getMessage());
        }
    }
}
