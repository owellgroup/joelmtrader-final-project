package com.wayaspot.forexbot.service;

import com.wayaspot.forexbot.config.AppProps;
import com.wayaspot.forexbot.entity.BotSession;
import com.wayaspot.forexbot.entity.Trade;
import com.wayaspot.forexbot.repo.BotSessionRepository;
import com.wayaspot.forexbot.repo.TradeRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

import static com.wayaspot.forexbot.service.EmailTemplates.*;

@Service
public class ReportService {
    private static final Logger log = LoggerFactory.getLogger(ReportService.class);
    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("dd MMM HH:mm").withZone(ZoneOffset.UTC);
    private final TradeRepository trades;
    private final BotSessionRepository sessions;
    private final PushService push;
    private final AppProps props;

    public ReportService(TradeRepository trades, BotSessionRepository sessions, PushService push, AppProps props) {
        this.trades = trades;
        this.sessions = sessions;
        this.push = push;
        this.props = props;
    }

    private String tradeRows(List<Trade> list, StringBuilder out) {
        List<List<String>> rows = new ArrayList<>();
        int n = 0;
        for (Trade t : list) {
            if (n++ >= 60) break;
            Double net = t.getNetProfit();
            rows.add(List.of(
                    t.getCloseTime() == null ? "-" : FMT.format(t.getCloseTime()),
                    esc(t.getSymbol()),
                    badge(t.getSide(), "BUY".equals(t.getSide()) ? "#059669" : "#dc2626"),
                    String.valueOf(t.getLots()),
                    String.valueOf(t.getOpenPrice()) + " &rarr; " + t.getClosePrice(),
                    "<b style=\"color:" + color(net) + "\">" + signed(net) + "</b>",
                    esc(t.getRemark())));
        }
        out.append(table(List.of("Closed", "Pair", "Side", "Lots", "Price", "Net P/L", "Remark"), rows));
        if (list.size() > 60) out.append("<p style=\"font-size:11px;color:#64748b\">+ ").append(list.size() - 60).append(" more trades in the app.</p>");
        return out.toString();
    }

    private String symbolTable(TradeStats s) {
        List<List<String>> rows = new ArrayList<>();
        s.bySymbol.forEach((k, v) -> rows.add(List.of("<b>" + esc(k) + "</b>", String.valueOf((int) v[0]),
                String.valueOf((int) v[1]), "<b style=\"color:" + color(v[2]) + "\">" + signed(v[2]) + "</b>")));
        return table(List.of("Pair", "Trades", "Wins", "Net"), rows);
    }

    public String sessionHtml(BotSession s, List<Trade> closed) {
        TradeStats st = TradeStats.of(closed);
        Double open = s.getOpeningBalance(), close = s.getClosingBalance();
        Double net = (open != null && close != null) ? close - open : st.net;
        String dur = s.getStoppedAt() == null ? "-" : fmtDuration(Duration.between(s.getStartedAt(), s.getStoppedAt()));
        StringBuilder b = new StringBuilder();
        b.append(kpis(List.of(
                new String[]{"Opening balance", money(open)},
                new String[]{"Closing balance", money(close)},
                new String[]{"Net result", signed(net), color(net)},
                new String[]{"Win rate", String.format("%.0f%% (%d/%d)", st.winRate(), st.wins, st.trades)},
                new String[]{"Profit factor", String.format("%.2f", st.profitFactor())},
                new String[]{"Session length", dur})));
        if (st.trades > 0) {
            b.append(section("Performance by pair")).append(symbolTable(st));
            b.append(section("Trades this session"));
            tradeRows(closed, b);
        } else {
            b.append("<p style=\"font-size:14px;color:#475569\">The bot did not find a setup that met the risk rules this session - capital was preserved.</p>");
        }
        return wrap(props.getBrandName(), props.getLogoUrl(), "Trading session summary",
                FMT.format(s.getStartedAt()) + " &rarr; " + (s.getStoppedAt() == null ? "now" : FMT.format(s.getStoppedAt())) + " UTC", b.toString());
    }

    @Async
    public void sendSessionReport(Long sessionId) {
        try {
            BotSession s = sessions.findById(sessionId).orElse(null);
            if (s == null) return;
            List<Trade> closed = trades.findBySessionIdOrderByOpenTimeAsc(sessionId).stream()
                    .filter(t -> "CLOSED".equals(t.getStatus())).toList();
            Double open = s.getOpeningBalance(), close = s.getClosingBalance();
            TradeStats st = TradeStats.of(closed);
            double net = (open != null && close != null) ? close - open : st.net;
            push.notify("SESSION_REPORT", "Session result " + signed(net),
                    String.format("%d trades · win rate %.0f%% · profit factor %.2f · net %s",
                            st.trades, st.winRate(), st.profitFactor(), signed(net)),
                    net < 0 ? "WARNING" : "INFO");
            s.setEmailSent(true);
            sessions.save(s);
        } catch (Exception e) {
            log.error("session report failed", e);
        }
    }

    /** Daily digest (23:55 UTC by default) - only when something happened today. */
    @Scheduled(cron = "${app.daily-report-cron}", zone = "UTC")
    public void dailyDigest() {
        try {
            sendDigest(LocalDate.now(ZoneOffset.UTC));
        } catch (Exception e) {
            log.error("daily digest failed", e);
        }
    }

    public boolean sendDigest(LocalDate day) {
        Instant from = day.atStartOfDay().toInstant(ZoneOffset.UTC);
        Instant to = from.plus(Duration.ofDays(1));
        List<Trade> closed = trades.findByStatusAndCloseTimeBetweenOrderByCloseTimeAsc("CLOSED", from, to);
        if (closed.isEmpty()) return false;
        TradeStats st = TradeStats.of(closed);
        StringBuilder b = new StringBuilder();
        b.append(kpis(List.of(
                new String[]{"Net P/L today", signed(st.net), color(st.net)},
                new String[]{"Trades closed", String.valueOf(st.trades)},
                new String[]{"Win rate", String.format("%.0f%%", st.winRate())},
                new String[]{"Profit factor", String.format("%.2f", st.profitFactor())},
                new String[]{"Best trade", signed(st.best), "#059669"},
                new String[]{"Worst trade", signed(st.worst), "#dc2626"})));
        b.append(section("By pair")).append(symbolTable(st)).append(section("All trades"));
        tradeRows(closed, b);
        push.notify("DAILY_REPORT", "Daily report " + day,
                String.format("Net %s · %d trades · win rate %.0f%% · profit factor %.2f",
                        signed(st.net), st.trades, st.winRate(), st.profitFactor()),
                st.net < 0 ? "WARNING" : "INFO");
        return true;
    }

    public boolean sendTest() {
        push.notify("TEST", "Test notification",
                "Push alerts are on. Entries, starts, stops, and reports arrive here instead of e-mail.", "INFO");
        return true;
    }

    private static String fmtDuration(Duration d) {
        long h = d.toHours(), m = d.toMinutesPart();
        return h > 0 ? h + "h " + m + "m" : m + "m";
    }
}
