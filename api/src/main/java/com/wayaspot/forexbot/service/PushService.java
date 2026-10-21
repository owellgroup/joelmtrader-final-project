package com.wayaspot.forexbot.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wayaspot.forexbot.config.AppProps;
import com.wayaspot.forexbot.entity.AppNotification;
import com.wayaspot.forexbot.entity.DeviceToken;
import com.wayaspot.forexbot.repo.AppNotificationRepository;
import com.wayaspot.forexbot.repo.DeviceTokenRepository;
import io.jsonwebtoken.Jwts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class PushService {
    private static final Logger log = LoggerFactory.getLogger(PushService.class);
    private final AppNotificationRepository notifications;
    private final DeviceTokenRepository devices;
    private final AppProps props;
    private final ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
    private String accessToken;
    private long accessTokenExpiry;

    public PushService(AppNotificationRepository notifications, DeviceTokenRepository devices, AppProps props, ObjectMapper mapper) {
        this.notifications = notifications;
        this.devices = devices;
        this.props = props;
        this.mapper = mapper;
    }

    @Transactional
    public DeviceToken register(String token, String platform) {
        DeviceToken row = devices.findByToken(token).orElseGet(DeviceToken::new);
        row.setToken(token);
        row.setPlatform(platform == null || platform.isBlank() ? "unknown" : platform);
        row.setUpdatedAt(Instant.now());
        return devices.save(row);
    }

    public List<AppNotification> latest() {
        return notifications.findTop200ByOrderByIdDesc();
    }

    public long unread() {
        return notifications.countBySeenFalse();
    }

    @Transactional
    public void markSeen(Long id) {
        notifications.findById(id).ifPresent(n -> {
            n.setSeen(true);
            notifications.save(n);
        });
    }

    @Transactional
    public int markAllSeen() {
        return notifications.markAllSeen();
    }

    /** Saves the alert for the in-app center, then pushes it to every registered phone. */
    public AppNotification notify(String type, String title, String body, String severity) {
        AppNotification n = save(type, title, body, severity);
        long id = n.getId();
        schedule(() -> deliver(id));
        return n;
    }

    /** Saves and pushes in this request, so the caller can see whether any phone was reached. */
    public Map<String, Object> notifyNow(String type, String title, String body, String severity) {
        AppNotification n = save(type, title, body, severity);
        return deliver(n.getId());
    }

    private AppNotification save(String type, String title, String body, String severity) {
        AppNotification n = new AppNotification();
        n.setType(type == null ? "ALERT" : type);
        n.setTitle(title == null ? "JoelMTrader" : title);
        n.setBody(body == null ? "" : body);
        n.setSeverity(severity == null ? "INFO" : severity);
        return notifications.save(n);
    }

    private void schedule(Runnable job) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    new Thread(job, "push").start();
                }
            });
        } else {
            new Thread(job, "push").start();
        }
    }

    public Map<String, Object> deliver(Long id) {
        Map<String, Object> out = new LinkedHashMap<>();
        AppNotification n = notifications.findById(id).orElse(null);
        out.put("saved", n != null);
        if (n == null) {
            out.put("sent", false);
            out.put("error", "Notification was not saved");
            return out;
        }
        List<DeviceToken> targets = devices.findAll();
        boolean configured = configured();
        out.put("configured", configured);
        out.put("devices", targets.size());
        if (targets.isEmpty()) {
            log.info("Push '{}' saved. No phone has registered yet.", n.getTitle());
            out.put("sent", false);
            out.put("delivered", 0);
            out.put("error", "No phone is registered. Open the Android app once while signed in, allow notifications, then send the test again.");
            return out;
        }
        if (!configured) {
            log.warn("Push '{}' saved, but FCM_PROJECT_ID / FCM_CLIENT_EMAIL / FCM_PRIVATE_KEY are not set.", n.getTitle());
            out.put("sent", false);
            out.put("delivered", 0);
            out.put("error", "Phone push is not configured on the server. The alert is saved and only appears when the app is opened.");
            return out;
        }
        int delivered = 0;
        String error = null;
        for (DeviceToken device : targets) {
            try {
                sendOne(device.getToken(), n);
                delivered++;
            } catch (Exception e) {
                error = e.getMessage();
                log.warn("Push to {} failed: {}", device.getPlatform(), e.getMessage());
            }
        }
        out.put("delivered", delivered);
        out.put("sent", delivered > 0);
        if (delivered == 0) out.put("error", error == null ? "Push was not accepted by Firebase" : error);
        return out;
    }

    private boolean configured() {
        return notBlank(props.getFcmProjectId()) && notBlank(props.getFcmClientEmail()) && notBlank(props.getFcmPrivateKey());
    }

    private static boolean notBlank(String s) {
        return s != null && !s.isBlank() && !s.contains("DemoPrivateKey");
    }

    private void sendOne(String token, AppNotification n) throws Exception {
        String bearer = googleAccessToken();
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("token", token);
        // Data-only on Android so the phone draws the alert itself, including when the app is closed.
        // A display payload is often delayed or dropped until the app is opened on some Android phones.
        message.put("data", Map.of(
                "id", String.valueOf(n.getId()),
                "type", n.getType() == null ? "ALERT" : n.getType(),
                "severity", n.getSeverity() == null ? "INFO" : n.getSeverity(),
                "title", n.getTitle() == null ? "JoelMTrader" : n.getTitle(),
                "body", n.getBody() == null ? "" : n.getBody()));
        message.put("android", Map.of(
                "priority", "HIGH",
                "ttl", "86400s"));
        message.put("apns", Map.of(
                "headers", Map.of("apns-priority", "10", "apns-push-type", "alert"),
                "payload", Map.of("aps", Map.of(
                        "alert", Map.of("title", n.getTitle(), "body", n.getBody() == null ? "" : n.getBody()),
                        "sound", "default",
                        "interruption-level", "time-sensitive"))));
        String json = mapper.writeValueAsString(Map.of("message", message));
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create("https://fcm.googleapis.com/v1/projects/" + props.getFcmProjectId().trim() + "/messages:send"))
                .timeout(Duration.ofSeconds(12))
                .header("Authorization", "Bearer " + bearer)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
        HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() == 404 || res.statusCode() == 400 && res.body() != null && res.body().contains("UNREGISTERED")) {
            devices.findByToken(token).ifPresent(devices::delete);
            return;
        }
        if (res.statusCode() >= 300) {
            throw new IllegalStateException("FCM " + res.statusCode() + " " + res.body());
        }
    }

    private synchronized String googleAccessToken() throws Exception {
        long now = System.currentTimeMillis();
        if (accessToken != null && now < accessTokenExpiry) return accessToken;
        String jwt = Jwts.builder()
                .issuer(props.getFcmClientEmail().trim())
                .subject(props.getFcmClientEmail().trim())
                .audience().add("https://oauth2.googleapis.com/token").and()
                .claim("scope", "https://www.googleapis.com/auth/firebase.messaging")
                .issuedAt(new Date(now))
                .expiration(new Date(now + 3600_000))
                .signWith(privateKey(), Jwts.SIG.RS256)
                .compact();
        String form = "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=" + jwt;
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create("https://oauth2.googleapis.com/token"))
                .timeout(Duration.ofSeconds(12))
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build();
        HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() >= 300) throw new IllegalStateException("Google token " + res.statusCode() + " " + res.body());
        @SuppressWarnings("unchecked")
        Map<String, Object> body = mapper.readValue(res.body(), Map.class);
        accessToken = String.valueOf(body.get("access_token"));
        int seconds = body.get("expires_in") instanceof Number num ? num.intValue() : 3600;
        accessTokenExpiry = now + Math.max(60, seconds - 120) * 1000L;
        return accessToken;
    }

    private PrivateKey privateKey() throws Exception {
        String pem = props.getFcmPrivateKey().replace("\\n", "\n")
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replaceAll("\\s", "");
        byte[] der = Base64.getDecoder().decode(pem);
        return KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(der));
    }
}
