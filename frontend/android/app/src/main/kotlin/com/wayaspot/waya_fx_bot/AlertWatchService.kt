package com.wayaspot.waya_fx_bot

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Keeps watching the server while the screen is closed and posts each new alert itself.
 * Opening the app is no longer required for the pop-up.
 */
class AlertWatchService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private var ticking = false
    private val tick = object : Runnable {
        override fun run() {
            Thread {
                try {
                    poll()
                } catch (_: Exception) {
                }
            }.start()
            handler.postDelayed(this, 12_000)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val url = intent?.getStringExtra("apiUrl")
        val token = intent?.getStringExtra("token")
        if (!url.isNullOrBlank() && !token.isNullOrBlank()) {
            getSharedPreferences(STORE, MODE_PRIVATE).edit().putString("apiUrl", url).putString("token", token).apply()
        }
        createChannels()
        val notice = watchNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(WATCH_ID, notice, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(WATCH_ID, notice)
        }
        if (!ticking) {
            ticking = true
            handler.post(tick)
        }
        return START_STICKY
    }

    /**
     * Android 15+ lets a "data sync" foreground service run about 6 hours a day, then calls this.
     * The service must stop here or the system crashes the app. Push (FCM) keeps delivering alerts after that.
     */
    override fun onTimeout(startId: Int, fgsType: Int) {
        ticking = false
        handler.removeCallbacks(tick)
        stopSelf()
    }

    override fun onDestroy() {
        ticking = false
        handler.removeCallbacks(tick)
        super.onDestroy()
    }

    private fun poll() {
        val prefs = getSharedPreferences(STORE, MODE_PRIVATE)
        val base = prefs.getString("apiUrl", null)?.trimEnd('/') ?: return
        val token = prefs.getString("token", null) ?: return
        if (token.isBlank()) return
        val conn = (URL("$base/api/notifications").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = 15000
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Accept", "application/json")
        }
        try {
            if (conn.responseCode != 200) return
            val text = conn.inputStream.bufferedReader().readText()
            val items = JSONObject(text).optJSONArray("items") ?: return
            if (!prefs.contains("pushLastId")) {
                var max = 0L
                for (i in 0 until items.length()) max = maxOf(max, items.optJSONObject(i)?.optLong("id", 0) ?: 0)
                prefs.edit().putLong("pushLastId", max).apply()
                return
            }
            var last = lastId(prefs)
            val fresh = mutableListOf<Triple<Long, String, String>>()
            for (i in 0 until items.length()) {
                val row = items.optJSONObject(i) ?: continue
                val id = row.optLong("id", 0)
                if (id > last) fresh.add(Triple(id, row.optString("title", "JoelMTrader"), row.optString("body", "")))
            }
            fresh.sortBy { it.first }
            val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            for ((id, title, body) in fresh) {
                nm.notify(id.toInt(), alert(title, body))
                if (id > last) last = id
            }
            if (fresh.isNotEmpty()) prefs.edit().putLong("pushLastId", last).apply()
        } finally {
            conn.disconnect()
        }
    }

    private fun lastId(prefs: android.content.SharedPreferences): Long {
        return when (val v = prefs.all["pushLastId"]) {
            is Int -> v.toLong()
            is Long -> v
            else -> 0L
        }
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel(ALERTS, "JoelMTrader alerts", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Entries, bot start and stop, and risk alerts"
            enableVibration(true)
        })
        nm.createNotificationChannel(NotificationChannel(WATCH, "JoelMTrader watch", NotificationManager.IMPORTANCE_MIN).apply {
            description = "Keeps alerts arriving while the app is closed"
            setSound(null, null)
        })
    }

    private fun watchNotification() = NotificationCompat.Builder(this, WATCH)
        .setSmallIcon(R.drawable.ic_stat_notify)
        .setContentTitle("JoelMTrader")
        .setContentText("Watching for trades")
        .setOngoing(true)
        .setSilent(true)
        .setPriority(NotificationCompat.PRIORITY_MIN)
        .setContentIntent(openApp())
        .build()

    private fun alert(title: String, body: String) = NotificationCompat.Builder(this, ALERTS)
        .setSmallIcon(R.drawable.ic_stat_notify)
        .setContentTitle(title)
        .setContentText(body)
        .setStyle(NotificationCompat.BigTextStyle().bigText(body))
        .setPriority(NotificationCompat.PRIORITY_MAX)
        .setCategory(NotificationCompat.CATEGORY_STATUS)
        .setAutoCancel(true)
        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        .setDefaults(NotificationCompat.DEFAULT_ALL)
        .setColor(0xFF0000FF.toInt())
        .setContentIntent(openApp())
        .build()

    private fun openApp(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    companion object {
        private const val WATCH_ID = 0x4a4d5401
        private const val ALERTS = "joelmtrader_alerts_v2"
        private const val WATCH = "joelmtrader_watch"
        private const val STORE = "joelmtrader_watch"

        fun start(context: Context, apiUrl: String?, token: String?) {
            val intent = Intent(context, AlertWatchService::class.java).apply {
                putExtra("apiUrl", apiUrl)
                putExtra("token", token)
            }
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, AlertWatchService::class.java))
        }
    }
}
