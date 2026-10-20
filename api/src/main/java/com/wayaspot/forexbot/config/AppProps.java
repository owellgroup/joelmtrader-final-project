package com.wayaspot.forexbot.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@Setter
@ConfigurationProperties(prefix = "app")
public class AppProps {
    private String jwtSecret;
    private int jwtExpiryDays = 365;
    private String engineUrl;
    private String engineApiKey;
    private String internalApiKey;
    private String adminUsername;
    private String adminPassword;
    private String mailFrom;
    private String reportTo;
    private String logoUrl;
    private String brandName;
    private String encryptionKey;
    private String dailyReportCron;
    private String fcmProjectId = "";
    private String fcmClientEmail = "";
    private String fcmPrivateKey = "";
}
