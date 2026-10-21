package com.wayaspot.forexbot.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wayaspot.forexbot.entity.AccountSnapshot;
import com.wayaspot.forexbot.entity.Trade;
import com.wayaspot.forexbot.entity.TransactionRecord;
import com.wayaspot.forexbot.repo.AccountSnapshotRepository;
import com.wayaspot.forexbot.repo.TradeRepository;
import com.wayaspot.forexbot.repo.TransactionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Map;

import static com.wayaspot.forexbot.service.Json.*;

/** Handles events pushed by the Python engine. */
@Service
public class EventService {
    private static final Logger log = LoggerFactory.getLogger(EventService.class);
    private final TradeRepository trades;
    private final TransactionRepository txs;
    private final AccountSnapshotRepository snapshots;
    private final LiveState live;
    private final PushService push;
    private final ObjectMapper mapper;

    public EventService(TradeRepository trades, TransactionRepository txs, AccountSnapshotRepository snapshots,
                        LiveState live, PushService push, ObjectMapper mapper) {
        this.trades = trades;
        this.txs = txs;
        this.snapshots = snapshots;
        this.live = live;
        this.push = push;
        this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    @Transactional
    public void handle(Map<String, Object> ev) {
        String type = str(ev.get("type"));
        Map<String, Object> d = ev.get("data") instanceof Map ? (Map<String, Object>) ev.get("data") : Map.of();
        Long sessionId = lng(ev.get("sessionId"));
        if (type == null) return;
        switch (type) {
            case "TRADE_OPENED" -> opened(d, sessionId);
            case "TRADE_FOUND" -> found(d);
            case "TRADE_CLOSED" -> closed(d, sessionId);
            case "SNAPSHOT" -> snapshot(d, sessionId);
            case "SCAN" -> live.setScan(d);
            case "ALERT" -> alert(d, sessionId);
            default -> log.debug("ignored event {}", type);
        }
    }

    private void opened(Map<String, Object> d, Long sessionId) {
        Long ticket = lng(d.get("ticket"));
        if (ticket == null) return;
        Trade t = trades.findByTicket(ticket).orElseGet(Trade::new);
        if ("CLOSED".equals(t.getStatus()) && t.getCloseTime() != null) return;
        t.setTicket(ticket);
        t.setSessionId(sessionId);
        t.setSymbol(str(d.get("symbol")));
        t.setSide(str(d.get("side")));
        t.setLots(dbl(d.get("lots")));
        t.setOpenPrice(dbl(d.get("openPrice")));
        t.setStopLoss(dbl(d.get("stopLoss")));
        t.setTakeProfit(dbl(d.get("takeProfit")));
        t.setOpenTime(epoch(d.get("openTime")) != null ? epoch(d.get("openTime")) : Instant.now());
        t.setScore(dbl(d.get("score")));
        t.setSetup(str(d.get("setup")));
        t.setBalanceBefore(dbl(d.get("balanceBefore")));
        t.setRiskAmount(dbl(d.get("riskAmount")));
        t.setRr(dbl(d.get("rr")));
        try {
            t.setReasons(mapper.writeValueAsString(d.get("reasons")));
        } catch (Exception ignored) { }
        t.setStatus("OPEN");
        trades.save(t);

        TransactionRecord tx = new TransactionRecord();
        tx.setType("TRADE_OPEN");
        tx.setTicket(ticket);
        tx.setSymbol(t.getSymbol());
        tx.setBalanceBefore(t.getBalanceBefore());
        tx.setBalanceAfter(t.getBalanceBefore());
        tx.setSessionId(sessionId);
        String detail = String.format("Opened %s %s %.2f lots @ %s | SL %s TP %s | %s (score %.0f)", t.getSide(), t.getSymbol(),
                t.getLots(), t.getOpenPrice(), t.getStopLoss(), t.getTakeProfit(), t.getSetup(), t.getScore() == null ? 0 : t.getScore());
        tx.setRemark(detail);
        txs.save(tx);
        push.notify("TRADE_OPENED", "Valid entry · " + t.getSymbol(), detail, "INFO");
    }

    private void found(Map<String, Object> d) {
        String symbol = str(d.get("symbol"));
        String side = str(d.get("side"));
        String setup = str(d.get("setup"));
        Double score = dbl(d.get("score"));
        Double rr = dbl(d.get("rr"));
        String body = String.format("%s %s · %s · score %.0f · R:R %s · entry %s  SL %s  TP %s",
                side == null ? "" : side, symbol == null ? "" : symbol, setup == null ? "" : setup,
                score == null ? 0 : score, rr == null ? "-" : rr, d.get("entry"), d.get("sl"), d.get("tp"));
        push.notify("TRADE_FOUND", "Trade found · " + (symbol == null ? "" : symbol), body, "INFO");
    }

    private void closed(Map<String, Object> d, Long sessionId) {
        Long ticket = lng(d.get("ticket"));
        if (ticket == null) return;
        Trade t = trades.findByTicket(ticket).orElseGet(() -> {
            Trade n = new Trade();
            n.setTicket(ticket);
            n.setSymbol(str(d.get("symbol")));
            n.setSessionId(sessionId);
            return n;
        });
        if ("CLOSED".equals(t.getStatus()) && t.getCloseTime() != null) return;
        double net = dbl(d.get("netProfit")) == null ? 0 : dbl(d.get("netProfit"));
        t.setClosePrice(dbl(d.get("closePrice")));
        t.setCloseTime(epoch(d.get("closeTime")) != null ? epoch(d.get("closeTime")) : Instant.now());
        t.setProfit(dbl(d.get("profit")));
        t.setCommission(dbl(d.get("commission")));
        t.setSwap(dbl(d.get("swap")));
        t.setNetProfit(net);
        t.setCloseReason(str(d.get("closeReason")));
        t.setRemark(str(d.get("remark")));
        t.setBalanceAfter(dbl(d.get("balanceAfter")));
        t.setResult(net > 0.005 ? "WIN" : (net < -0.005 ? "LOSS" : "BREAKEVEN"));
        t.setStatus("CLOSED");
        trades.save(t);

        TransactionRecord tx = new TransactionRecord();
        tx.setType("TRADE_CLOSE");
        tx.setTicket(ticket);
        tx.setSymbol(t.getSymbol());
        tx.setAmount(net);
        tx.setBalanceAfter(t.getBalanceAfter());
        tx.setBalanceBefore(t.getBalanceAfter() == null ? null : t.getBalanceAfter() - net);
        tx.setSessionId(sessionId != null ? sessionId : t.getSessionId());
        tx.setRemark(t.getResult() + " - " + t.getRemark());
        txs.save(tx);
        String money = t.getNetProfit() == null ? "" : String.format(" · P/L %.2f", t.getNetProfit());
        push.notify("TRADE_CLOSED", t.getResult() + " · " + t.getSymbol(),
                (t.getSide() == null ? "" : t.getSide() + " ") + t.getSymbol() + " closed" + money
                        + (t.getCloseReason() == null ? "" : " · " + t.getCloseReason()),
                net < -0.005 ? "WARNING" : "INFO");
    }

    private void snapshot(Map<String, Object> d, Long sessionId) {
        AccountSnapshot s = new AccountSnapshot();
        s.setBalance(dbl(d.get("balance")));
        s.setEquity(dbl(d.get("equity")));
        s.setMargin(dbl(d.get("margin")));
        s.setFreeMargin(dbl(d.get("freeMargin")));
        Long op = lng(d.get("openPositions"));
        s.setOpenPositions(op == null ? 0 : op.intValue());
        s.setSessionId(sessionId);
        snapshots.save(s);
    }

    private void alert(Map<String, Object> d, Long sessionId) {
        String subject = str(d.get("subject")), message = str(d.get("message"));
        String severity = d.get("severity") == null ? "WARNING" : str(d.get("severity"));
        if ("halt".equals(str(d.get("key")))) {
            TransactionRecord tx = new TransactionRecord();
            tx.setType("HALT");
            tx.setRemark(message);
            tx.setSessionId(sessionId);
            txs.save(tx);
        }
        push.notify("ALERT", subject == null ? "Bot alert" : subject, message == null ? "" : message, severity);
    }
}
