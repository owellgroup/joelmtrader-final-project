package com.wayaspot.forexbot.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.wayaspot.forexbot.service.EngineClient;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/market")
public class MarketController {
    private final EngineClient engine;

    public MarketController(EngineClient engine) {
        this.engine = engine;
    }

    @GetMapping("/quotes")
    public JsonNode quotes() {
        return engine.get("/quotes");
    }

    @GetMapping("/scan")
    public JsonNode scan() {
        return engine.get("/scan");
    }

    @PostMapping("/scan/now")
    public JsonNode scanNow() {
        return engine.post("/scan/now", null);
    }

    @GetMapping("/analysis/{symbol}")
    public JsonNode analysis(@PathVariable String symbol, @RequestParam(defaultValue = "M5") String tf,
                             @RequestParam(defaultValue = "150") int bars) {
        String canon = symbol == null ? "" : symbol.replace("/", "").replace(".", "").replace("-", "").toUpperCase();
        if (canon.equals("GOLD") || canon.equals("XAU")) canon = "XAUUSD";
        String timeframe = tf == null ? "M5" : tf.toUpperCase();
        if (!canon.matches("[A-Z]{6}") || !timeframe.matches("M1|M5|M10|M15|M30|H1|H4|D1"))
            throw new IllegalArgumentException("unsupported symbol/timeframe — use XAUUSD, GBPJPY, EURJPY, EURUSD or GBPUSD");
        return engine.get("/analysis/" + canon + "?tf=" + timeframe + "&bars=" + bars);
    }

    @GetMapping("/news")
    public JsonNode news() {
        return engine.get("/news");
    }
}
