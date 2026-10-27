package com.wayaspot.forexbot.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wayaspot.forexbot.entity.AccountSnapshot;
import com.wayaspot.forexbot.entity.Trade;
import com.wayaspot.forexbot.repo.AccountSnapshotRepository;
import com.wayaspot.forexbot.repo.TradeRepository;
import com.wayaspot.forexbot.service.BotService;
import com.wayaspot.forexbot.service.EngineClient;
import com.wayaspot.forexbot.service.EngineException;
import com.wayaspot.forexbot.service.LiveState;
import com.wayaspot.forexbot.service.MarketSymbols;
import com.wayaspot.forexbot.service.TradeStats;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.*;

@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {
    private final BotService bot;
    private final EngineClient engine;
    private final TradeRepository trades;
    private final AccountSnapshotRepository snapshots;
    private final LiveState live;
    private final ObjectMapper mapper;

    public DashboardController(BotService bot, EngineClient engine, TradeRepository trades,
                               AccountSnapshotRepository snapshots, LiveState live, ObjectMapper mapper) {
        this.bot = bot;
        this.engine = engine;
        this.trades = trades;
        this.snapshots = snapshots;
        this.live = live;
        this.mapper = mapper;
    }

    @GetMapping
    public Map<String, Object> dashboard() {
        Map<String, Object> out = new LinkedHashMap<>();
        Map<String, Object> st = bot.status();
        out.put("bot", st);

        List<AccountSnapshot> snaps = snapshots.findTop300ByOrderByCapturedAtDesc();
        Object account = null;
        try {
            account = engine.get("/account");
        } catch (EngineException e) {
            if (!snaps.isEmpty()) {
                Map<String, Object> a = new LinkedHashMap<>();
                a.put("balance", snaps.get(0).getBalance());
                a.put("equity", snaps.get(0).getEquity());
                a.put("stale", true);
                account = a;
            }
        }
        out.put("account", account);

        List<Trade> closed = trades.findByStatus("CLOSED");
        Instant dayStart = LocalDate.now(ZoneOffset.UTC).atStartOfDay().toInstant(ZoneOffset.UTC);
        List<Trade> today = closed.stream().filter(t -> t.getCloseTime() != null && !t.getCloseTime().isBefore(dayStart)).toList();
        out.put("all", TradeStats.of(closed).toMap());
        out.put("today", TradeStats.of(today).toMap());
        out.put("openTrades", trades.findByStatus("OPEN").size());
        out.put("closedTrades", closed.size());

        List<Map<String, Object>> curve = new ArrayList<>();
        for (int i = snaps.size() - 1; i >= 0; i--) {
            AccountSnapshot s = snaps.get(i);
            Map<String, Object> p = new LinkedHashMap<>();
            p.put("time", s.getCapturedAt());
            p.put("equity", s.getEquity());
            p.put("balance", s.getBalance());
            curve.add(p);
        }
        out.put("equityCurve", curve);

        JsonNode scanNode = null;
        try {
            scanNode = engine.get("/scan");
        } catch (EngineException ignored) {
            Object cached = live.getScan();
            if (cached instanceof JsonNode node) scanNode = node;
            else if (cached != null) scanNode = mapper.valueToTree(cached);
        }
        out.put("scan", MarketSymbols.ensureScan(scanNode, mapper));
        return out;
    }
}
