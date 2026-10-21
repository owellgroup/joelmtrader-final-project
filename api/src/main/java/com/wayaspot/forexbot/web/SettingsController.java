package com.wayaspot.forexbot.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wayaspot.forexbot.service.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/settings")
public class SettingsController {
    public record Mt5Request(String login, String server, String password) { }

    private final SettingsService settings;
    private final CryptoService crypto;
    private final EngineClient engine;
    private final BotService bot;
    private final ReportService reports;
    private final ObjectMapper mapper;

    public SettingsController(SettingsService settings, CryptoService crypto, EngineClient engine, BotService bot,
                              ReportService reports, ObjectMapper mapper) {
        this.settings = settings;
        this.crypto = crypto;
        this.engine = engine;
        this.bot = bot;
        this.reports = reports;
        this.mapper = mapper;
    }

    @GetMapping("/mt5")
    public Map<String, Object> mt5() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("login", settings.get("mt5.login").orElse(""));
        m.put("server", settings.get("mt5.server").orElse(""));
        m.put("hasPassword", settings.get("mt5.password").isPresent());
        try {
            m.put("status", engine.get("/mt5/status"));
        } catch (EngineException e) {
            m.put("status", Map.of("connected", false, "message", e.getMessage()));
        }
        return m;
    }

    @PutMapping("/mt5")
    @PreAuthorize("hasRole('SUPER_ADMIN')")
    public Map<String, Object> saveMt5(@RequestBody Mt5Request r) {
        if (r.login() != null && !r.login().isBlank()) settings.set("mt5.login", r.login().trim());
        if (r.server() != null && !r.server().isBlank()) settings.set("mt5.server", r.server().trim());
        if (r.password() != null && !r.password().isBlank()) settings.set("mt5.password", crypto.encrypt(r.password()));
        JsonNode res = bot.pushMt5Credentials();
        Map<String, Object> m = mt5();
        m.put("connectResult", res);
        return m;
    }

    @PostMapping("/mt5/connect")
    public JsonNode connect() {
        return bot.pushMt5Credentials();
    }

    @GetMapping("/risk")
    public JsonNode risk() {
        return engine.get("/config");
    }

    @PutMapping("/risk")
    @PreAuthorize("hasRole('SUPER_ADMIN')")
    public JsonNode saveRisk(@RequestBody Map<String, Object> cfg) throws Exception {
        JsonNode applied = engine.put("/config", cfg);
        settings.set("risk.config", mapper.writeValueAsString(applied));
        return applied;
    }

    @PostMapping("/test-email")
    public Map<String, Object> testEmail() {
        return reports.sendTest();
    }
}
