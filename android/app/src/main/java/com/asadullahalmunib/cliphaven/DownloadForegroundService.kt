package com.asadullahalmunib.cliphaven

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class DownloadForegroundService : Service() {

    companion object {
        const val CHANNEL_ID = "cliphaven_downloads_channel"
        const val NOTIFICATION_ID = 8765

        const val ACTION_START = "com.asadullahalmunib.cliphaven.action.START"
        const val ACTION_STOP = "com.asadullahalmunib.cliphaven.action.STOP"

        const val EXTRA_TITLE = "extra_title"
        const val EXTRA_DETAIL = "extra_detail"
        const val EXTRA_PERCENT = "extra_percent"
        const val EXTRA_INDETERMINATE = "extra_indeterminate"

        @Volatile
        private var instance: DownloadForegroundService? = null

        fun start(context: Context, title: String, detail: String) {
            try {
                val intent = Intent(context, DownloadForegroundService::class.java).apply {
                    action = ACTION_START
                    putExtra(EXTRA_TITLE, title)
                    putExtra(EXTRA_DETAIL, detail)
                    putExtra(EXTRA_PERCENT, 0)
                    putExtra(EXTRA_INDETERMINATE, true)
                }
                ContextCompat.startForegroundService(context, intent)
            } catch (_: Throwable) {
            }
        }

        fun update(context: Context, title: String, detail: String, percent: Int, indeterminate: Boolean) {
            try {
                val svc = instance
                if (svc != null) {
                    svc.updateNotification(title, detail, percent, indeterminate)
                }
            } catch (_: Throwable) {
            }
        }

        fun stop(context: Context) {
            try {
                instance?.stopForegroundAndSelf()
                context.stopService(Intent(context, DownloadForegroundService::class.java))
            } catch (_: Throwable) {
            }
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var notificationManager: NotificationManager? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
        createNotificationChannel()
        acquireWakeLock()
    }

    private fun acquireWakeLock() {
        try {
            if (wakeLock == null) {
                val powerManager = getSystemService(Context.POWER_SERVICE) as? PowerManager
                wakeLock = powerManager?.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "ClipHaven::DownloadWakeLock"
                )?.apply {
                    setReferenceCounted(false)
                    acquire(3 * 3600 * 1000L)
                }
            }
        } catch (_: Throwable) {
        }
    }

    private fun releaseWakeLock() {
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
            }
        } catch (_: Throwable) {
        } finally {
            wakeLock = null
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "ClipHaven Downloads",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows live download and video conversion progress"
                setShowBadge(false)
            }
            notificationManager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(title: String, detail: String, percent: Int, indeterminate: Boolean): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            openIntent,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT else PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title.ifEmpty { "ClipHaven Downloading…" })
            .setContentText(detail)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)

        if (indeterminate) {
            builder.setProgress(100, 0, true)
        } else if (percent in 0..100) {
            builder.setProgress(100, percent, false)
        }

        return builder.build()
    }

    fun updateNotification(title: String, detail: String, percent: Int, indeterminate: Boolean) {
        try {
            val notif = buildNotification(title, detail, percent, indeterminate)
            notificationManager?.notify(NOTIFICATION_ID, notif)
        } catch (_: Throwable) {
        }
    }

    fun stopForegroundAndSelf() {
        releaseWakeLock()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                stopForeground(STOP_FOREGROUND_REMOVE)
            } else {
                @Suppress("DEPRECATION")
                stopForeground(true)
            }
        } catch (_: Throwable) {
        }
        try {
            stopSelf()
        } catch (_: Throwable) {
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        instance = this
        val action = intent?.action ?: ACTION_START
        if (action == ACTION_STOP) {
            stopForegroundAndSelf()
            return START_NOT_STICKY
        }

        acquireWakeLock()
        val title = intent?.getStringExtra(EXTRA_TITLE) ?: "ClipHaven"
        val detail = intent?.getStringExtra(EXTRA_DETAIL) ?: "Downloading media…"
        val percent = intent?.getIntExtra(EXTRA_PERCENT, 0) ?: 0
        val indeterminate = intent?.getBooleanExtra(EXTRA_INDETERMINATE, false) ?: false

        val notif = buildNotification(title, detail, percent, indeterminate)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(NOTIFICATION_ID, notif)
            }
        } catch (_: Throwable) {
        }

        return START_NOT_STICKY
    }

    override fun onDestroy() {
        if (instance === this) {
            instance = null
        }
        releaseWakeLock()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
