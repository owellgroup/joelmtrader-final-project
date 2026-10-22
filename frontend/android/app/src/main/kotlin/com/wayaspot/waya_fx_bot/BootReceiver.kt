package com.wayaspot.waya_fx_bot

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Starts the alert watcher again after the phone restarts or the app is updated, using the server address
 * and sign-in saved the last time the app was opened. Some Android versions block this; push (FCM) still works.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val prefs = context.getSharedPreferences("joelmtrader_watch", Context.MODE_PRIVATE)
        if (prefs.getString("apiUrl", null).isNullOrBlank() || prefs.getString("token", null).isNullOrBlank()) return
        try {
            AlertWatchService.start(context, null, null)
        } catch (_: Exception) {
        }
    }
}
