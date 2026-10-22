package com.wayaspot.forexbot.web;

import com.wayaspot.forexbot.service.PushService;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class NotificationController {
    public record DeviceRequest(String token, String platform) { }

    private final PushService push;

    public NotificationController(PushService push) {
        this.push = push;
    }

    @GetMapping("/api/notifications")
    public Map<String, Object> list() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("items", push.latest());
        m.put("unread", push.unread());
        return m;
    }

    @GetMapping("/api/notifications/push-status")
    public Map<String, Object> pushStatus() {
        return push.status();
    }

    @PostMapping("/api/notifications/{id}/read")
    public Map<String, Object> read(@PathVariable Long id) {
        push.markSeen(id);
        return Map.of("unread", push.unread());
    }

    @PostMapping("/api/notifications/read-all")
    public Map<String, Object> readAll() {
        push.markAllSeen();
        return Map.of("unread", push.unread());
    }

    @PostMapping("/api/devices")
    public Map<String, Object> register(@RequestBody DeviceRequest body) {
        if (body.token() == null || body.token().isBlank()) {
            throw new IllegalArgumentException("token is required");
        }
        var saved = push.register(body.token().trim(), body.platform());
        return Map.of("id", saved.getId(), "platform", saved.getPlatform());
    }
}
