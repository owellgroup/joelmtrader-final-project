package com.wayaspot.forexbot.repo;

import com.wayaspot.forexbot.entity.AppNotification;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface AppNotificationRepository extends JpaRepository<AppNotification, Long> {
    List<AppNotification> findTop200ByOrderByIdDesc();

    long countBySeenFalse();

    @Modifying(clearAutomatically = true)
    @Query("update AppNotification n set n.seen = true where n.seen = false")
    int markAllSeen();
}
