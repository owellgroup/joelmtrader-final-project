package com.wayaspot.forexbot.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.Instant;

@Entity
@Table(name = "device_tokens", uniqueConstraints = @UniqueConstraint(columnNames = "token"))
@Getter
@Setter
public class DeviceToken {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 512)
    private String token;
    private String platform;
    private Instant updatedAt = Instant.now();
}
