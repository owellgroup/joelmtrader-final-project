package com.wayaspot.forexbot.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * E-mail delivery is turned off. Bot alerts, reports, and tests are push notifications.
 */
@Service
public class EmailService {
    private static final Logger log = LoggerFactory.getLogger(EmailService.class);

    public boolean sendNow(String subject, String html) {
        log.info("E-mail skipped for '{}'. Push notifications are used instead.", subject);
        return false;
    }

    public void sendAsync(String subject, String html) {
        sendNow(subject, html);
    }

    public void sendAlert(String subject, String message, String severity) {
        sendNow("[" + severity + "] " + subject, message);
    }
}
