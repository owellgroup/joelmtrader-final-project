package com.wayaspot.forexbot.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.wayaspot.forexbot.entity.AccountSnapshot;
import com.wayaspot.forexbot.entity.BotSession;
import com.wayaspot.forexbot.entity.TransactionRecord;
import com.wayaspot.forexbot.repo.AccountSnapshotRepository;
import com.wayaspot.forexbot.repo.BotSessionRepository;
import com.wayaspot.forexbot.repo.TransactionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class BotService {
    private static final Logger log = LoggerFactory.getLogger(BotService.class);
    private final EngineClient engine;
    private final BotSessionRepository sessions;
    private final TransactionRepository txs;
    private final AccountSnapshotRepository snapshots;
    private final SettingsService settings;
    private final CryptoService crypto;
    private final ReportService reports;
    private final PushService push;
    private volatile long engineDownSince = 0;
    private volatile long lastConnectTry = 0;
    private volatile long lastDownAlert = 0;

    public BotService(EngineClient engine, BotSessionRepository sessions, TransactionRepository txs,
                      AccountSnapshotRepository snapshots, SettingsService settings, CryptoService crypto,
                      ReportService reports, PushService push) {
        this.engine = engine;
        this.sessions = sessions;
        this.txs = txs;
        this.snapshots = snapshots;
        this.settings = settings;
        this.crypto = crypto;
        this.reports = reports;
        this.push = push;
    }

    public Optional<BotSession> running() {
        return sessions.findFirstByStatusOrderByIdDesc("RUNNING");
    }

    public synchronized Map<String, Object> start() {
        if (running().isPresent()) return status();
        JsonNode mt5 = engine.get("/mt5/status");
        if (!mt5.path("connected").asBoolean(false)) {
            pushMt5Credentials();
            mt5 = engine.get("/mt5/status");
        }
        if (!mt5.path("connected").asBoolean(false)) {
            throw new EngineException("MT5 is not connected. Open Settings, enter your broker account and press Connect. "
                    + mt5.path("message").asText(""), 409);
        }
        settings.get("risk.config").ifPresent(cfg -> {
            try { engine.put("/config", new com.fasterxml.jackson.databind.ObjectMapper().readValue(cfg, Map.class)); }
            catch (Exception e) { log.warn("could not push risk config: {}", e.getMessage()); }
        });
        JsonNode acct = engine.get("/account");
        BotSession s = new BotSession();
        s.setOpeningBalance(acct.path("balance").asDouble());
        sessions.save(s);
        try {
            engine.post("/bot/start", Map.of("sessionId", s.getId()));
        } catch (EngineException e) {
            s.setStatus("FAILED");
            s.setNote(e.getMessage());
            s.setStoppedAt(Instant.now());
            sessions.save(s);
            throw e;
        }
        TransactionRecord tx = new TransactionRecord();
        tx.setType("BOT_START");
        tx.setSessionId(s.getId());
        tx.setBalanceBefore(s.getOpeningBalance());
        tx.setBalanceAfter(s.getOpeningBalance());
        tx.setRemark("Bot started - opening balance " + EmailTemplates.money(s.getOpeningBalance()));
        txs.save(tx);
        push.notify("BOT_START", "Bot started", "Scanning the markets. Opening balance " + EmailTemplates.money(s.getOpeningBalance()) + ".", "INFO");
        return status();
    }

    public synchronized Map<String, Object> stop(boolean closePositions) {
        Optional<BotSession> run = running();
        if (run.isEmpty()) return status();
        BotSession s = run.get();
        Double closing = null;
        String note = null;
        try {
            JsonNode res = engine.post("/bot/stop", Map.of("closePositions", closePositions));
            if (res.path("account").has("balance")) closing = res.path("account").path("balance").asDouble();
        } catch (EngineException e) {
            note = "Engine unreachable while stopping: " + e.getMessage();
            List<AccountSnapshot> last = snapshots.findTop300ByOrderByCapturedAtDesc();
            if (!last.isEmpty()) closing = last.get(0).getBalance();
        }
        s.setClosingBalance(closing);
        s.setStoppedAt(Instant.now());
        s.setStatus("STOPPED");
        s.setNote(note);
        sessions.save(s);
        TransactionRecord tx = new TransactionRecord();
        tx.setType("BOT_STOP");
        tx.setSessionId(s.getId());
        tx.setBalanceBefore(s.getOpeningBalance());
        tx.setBalanceAfter(closing);
        tx.setAmount(closing == null || s.getOpeningBalance() == null ? null : closing - s.getOpeningBalance());
        String stopNote = "Bot stopped" + (closePositions ? ". Open positions were closed." : ". Open trades keep their stop-loss and take-profit.");
        tx.setRemark(stopNote);
        txs.save(tx);
        push.notify("BOT_STOP", "Bot stopped", stopNote, "WARNING");
        reports.sendSessionReport(s.getId());
        return status();
    }

    public Map<String, Object> status() {
        Map<String, Object> m = new LinkedHashMap<>();
        Optional<BotSession> run = running();
        m.put("running", run.isPresent());
        run.ifPresent(s -> m.put("session", s));
        try {
            m.put("engine", engine.get("/bot/status"));
            m.put("engineOnline", true);
        } catch (EngineException e) {
            m.put("engineOnline", false);
            m.put("engineError", e.getMessage());
        }
        return m;
    }

    /** (Re)sends the stored MT5 credentials to the engine. */
    public JsonNode pushMt5Credentials() {
        Map<String, Object> body = new LinkedHashMap<>();
        settings.get("mt5.login").ifPresent(v -> body.put("login", v));
        settings.get("mt5.server").ifPresent(v -> body.put("server", v));
        settings.get("mt5.password").ifPresent(v -> {
            try { body.put("password", crypto.decrypt(v)); } catch (Exception e) { log.warn("cannot decrypt MT5 password"); }
        });
        return engine.post("/mt5/connect", body);
    }

    /** Keeps the engine connected and the bot alive: "once started it keeps going until you press stop". */
    @Scheduled(fixedDelay = 30000, initialDelay = 25000)
    public void watchdog() {
        try {
            JsonNode mt5 = engine.get("/mt5/status");
            engineDownSince = 0;
            if (!mt5.path("connected").asBoolean(false) && settings.get("mt5.login").isPresent()
                    && System.currentTimeMillis() - lastConnectTry > 60000) {
                lastConnectTry = System.currentTimeMillis();
                log.info("MT5 not connected - re-sending stored credentials");
                pushMt5Credentials();
            }
            Optional<BotSession> run = running();
            if (run.isPresent()) {
                JsonNode st = engine.get("/bot/status");
                if (!st.path("running").asBoolean(false)) {
                    log.warn("Session {} is RUNNING but the engine is idle - restarting the bot loop", run.get().getId());
                    engine.post("/bot/start", Map.of("sessionId", run.get().getId()));
                }
            }
        } catch (EngineException e) {
            long now = System.currentTimeMillis();
            if (engineDownSince == 0) engineDownSince = now;
            if (running().isPresent() && now - engineDownSince > 300_000 && now - lastDownAlert > 1_800_000) {
                lastDownAlert = now;
                push.notify("ENGINE_DOWN", "Trading engine unreachable",
                        "The trading engine has been unreachable for over 5 minutes while the bot was running. Open positions keep their stop-loss and take-profit at the broker.", "CRITICAL");
            }
        } catch (Exception e) {
            log.warn("watchdog error: {}", e.getMessage());
        }
    }
}
