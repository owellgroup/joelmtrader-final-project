package com.wayaspot.forexbot.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wayaspot.forexbot.service.EngineClient;
import com.wayaspot.forexbot.service.EngineException;
import com.wayaspot.forexbot.service.MarketSymbols;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/market")
public class MarketController {
    private final EngineClient engine;
    private final ObjectMapper mapper;

    public MarketController(EngineClient engine, ObjectMapper mapper) {
        this.engine = engine;
        this.mapper = mapper;
    }

    @GetMapping("/quotes")
    public JsonNode quotes() {
        return engine.get("/quotes");
    }

    @GetMapping("/scan")
    public JsonNode scan() {
        try {
            return MarketSymbols.ensureScan(engine.get("/scan"), mapper);
        } catch (EngineException e) {
            return MarketSymbols.ensureScan(null, mapper);
        }
    }

    @PostMapping("/scan/now")
    public JsonNode scanNow() {
        return MarketSymbols.ensureScan(engine.post("/scan/now", null), mapper);
    }

    @GetMapping("/analysis/{symbol}")
    public JsonNode analysis(@PathVariable String symbol, @RequestParam(defaultValue = "M5") String tf,
                             @RequestParam(defaultValue = "150") int bars) {
        String canon = symbol == null ? "" : symbol.replace("/", "").replace(".", "").replace("-", "").toUpperCase();
        if (canon.equals("GOLD") || canon.equals("XAU")) canon = "XAUUSD";
        String timeframe = tf == null ? "M5" : tf.toUpperCase();
        if ("1H".equals(timeframe)) timeframe = "H1";
        if ("4H".equals(timeframe)) timeframe = "H4";
        if ("1D".equals(timeframe) || "D".equals(timeframe)) timeframe = "D1";
        if (!MarketSymbols.isKnown(canon)) {
            throw new IllegalArgumentException("unsupported symbol — use XAUUSD, GBPJPY, EURJPY, EURUSD or GBPUSD");
        }
        if (!timeframe.matches("M1|M5|M10|M15|M30|H1|H4|D1")) {
            throw new IllegalArgumentException("unsupported timeframe — use M1, M5, M10, M15, M30, H1, H4 or D1");
        }
        try {
            return engine.get("/analysis/" + canon + "?tf=" + timeframe + "&bars=" + bars);
        } catch (EngineException e) {
            // Older engine builds reject GBPJPY/EURJPY. Keep the chart page alive with a clear status.
            String msg = e.getMessage() == null ? "Trading engine rejected this chart" : e.getMessage();
            if (msg.toLowerCase().contains("unsupported") || e.getStatus() == 400) {
                return MarketSymbols.emptyChart(mapper, canon, timeframe,
                        "Engine is still on an old build for " + canon + ". Redeploy the engine container, then retry. (" + msg + ")");
            }
            throw e;
        }
    }

    @GetMapping("/news")
    public JsonNode news() {
        return engine.get("/news");
    }

    @GetMapping("/universe")
    public JsonNode universe() {
        return mapper.createObjectNode()
                .put("build", "2026-10-27-jpy-fix")
                .set("symbols", mapper.valueToTree(MarketSymbols.ALL));
    }
}
