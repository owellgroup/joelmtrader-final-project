package com.wayaspot.forexbot.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.Instant;

@Entity
@Table(name = "app_notifications")
@Getter
@Setter
public class AppNotification {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private Instant createdAt = Instant.now();
    private String type;
    private String title;
    @Column(length = 2000)
    private String body;
    private String severity = "INFO";
    @Column(name = "seen")
    private boolean seen;
}
