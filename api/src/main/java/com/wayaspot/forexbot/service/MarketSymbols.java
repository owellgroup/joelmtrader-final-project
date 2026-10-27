package com.wayaspot.forexbot.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Keeps all five live pairs visible even when an older engine build omits them. */
public final class MarketSymbols {
    public static final List<String> ALL = List.of("XAUUSD", "GBPJPY", "EURJPY", "EURUSD", "GBPUSD");
    public static final List<String> PRIORITY = List.of("XAUUSD", "GBPJPY", "EURJPY");

    private MarketSymbols() {}

    public static boolean isKnown(String symbol) {
        return symbol != null && ALL.contains(symbol.toUpperCase());
    }

    public static JsonNode ensureScan(JsonNode scan, ObjectMapper mapper) {
        ObjectNode out = scan != null && scan.isObject() ? ((ObjectNode) scan).deepCopy()
                : mapper.createObjectNode();
        Map<String, JsonNode> bySymbol = new LinkedHashMap<>();
        JsonNode rankings = out.get("rankings");
        if (rankings != null && rankings.isArray()) {
            for (JsonNode row : rankings) {
                if (row != null && row.hasNonNull("symbol")) {
                    bySymbol.put(row.get("symbol").asText(), row);
                }
            }
        }
        ArrayNode next = mapper.createArrayNode();
        for (String symbol : ALL) {
            JsonNode row = bySymbol.get(symbol);
            if (row != null) {
                next.add(row);
            } else {
                next.add(pending(mapper, symbol));
            }
        }
        out.set("rankings", next);
        if (!out.has("why") || out.get("why").asText("").isBlank()) {
            out.put("why", "Waiting for the trading engine to finish scanning all five pairs.");
        }
        return out;
    }

    public static ObjectNode pending(ObjectMapper mapper, String symbol) {
        ObjectNode row = mapper.createObjectNode();
        row.put("symbol", symbol);
        row.put("direction", 0);
        row.put("side", "WAIT");
        row.put("score", 0);
        row.put("rankScore", -1);
        row.put("setup", "WAITING");
        row.put("bias", 0);
        row.putNull("price");
        row.putNull("spread");
        row.putNull("plan");
        row.put("rr", 0);
        row.put("lots", 0);
        row.put("riskAmount", 0);
        row.put("riskPctAtMinLot", 0);
        row.set("components", mapper.createObjectNode());
        row.set("reasons", mapper.createArrayNode());
        row.set("penalties", mapper.createArrayNode());
        row.put("priority", PRIORITY.contains(symbol));
        row.putNull("accountFix");
        row.putNull("affordability");
        row.put("tradable", false);
        ArrayNode blocked = mapper.createArrayNode();
        blocked.add("Waiting for market data from MT5 for " + symbol);
        row.set("blockedReasons", blocked);
        row.set("timeframes", mapper.createObjectNode());
        row.put("htfLock", "WAIT");
        row.put("story", "Engine has not returned a score for " + symbol + " yet.");
        return row;
    }

    public static ObjectNode emptyChart(ObjectMapper mapper, String symbol, String tf, String error) {
        ObjectNode out = mapper.createObjectNode();
        out.put("symbol", symbol);
        out.put("tf", tf);
        out.put("tfSeconds", tfSeconds(tf));
        out.put("digits", 5);
        out.set("candles", mapper.createArrayNode());
        out.set("indicators", mapper.createObjectNode());
        out.set("zones", mapper.createArrayNode());
        out.set("trendlines", mapper.createArrayNode());
        out.set("orderBlocks", mapper.createArrayNode());
        out.set("fvgs", mapper.createArrayNode());
        out.set("swings", mapper.createArrayNode());
        out.set("markers", mapper.createArrayNode());
        out.set("pivots", mapper.createArrayNode());
        out.set("sessions", mapper.createArrayNode());
        out.set("liquidity", mapper.createArrayNode());
        ObjectNode structure = mapper.createObjectNode();
        structure.put("label", "waiting");
        structure.putNull("bos");
        structure.putNull("choch");
        out.set("structure", structure);
        out.putNull("plan");
        out.set("positions", mapper.createArrayNode());
        out.putNull("bid");
        out.putNull("ask");
        ObjectNode analysis = mapper.createObjectNode();
        analysis.put("bias", "WAIT");
        analysis.put("htfLock", "WAIT");
        analysis.put("story", error);
        analysis.set("stack", mapper.createObjectNode());
        analysis.set("tools", mapper.createArrayNode());
        out.set("analysis", analysis);
        out.put("error", error);
        return out;
    }

    private static int tfSeconds(String tf) {
        return switch (tf == null ? "M5" : tf.toUpperCase()) {
            case "M1" -> 60;
            case "M5" -> 300;
            case "M10" -> 600;
            case "M15" -> 900;
            case "M30" -> 1800;
            case "H1" -> 3600;
            case "H4" -> 14400;
            case "D1" -> 86400;
            default -> 300;
        };
    }
}
