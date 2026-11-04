package com.asadullahalmunib.cliphaven

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class DownloadForegroundService : Service() {

    companion object {
        const val CHANNEL_ID = "cliphaven_downloads_channel"
        const val NOTIFICATION_ID = 8765
        const val COMPLETE_NOTIFICATION_ID = 8766

        const val ACTION_START = "com.asadullahalmunib.cliphaven.action.START"
        const val ACTION_STOP = "com.asadullahalmunib.cliphaven.action.STOP"
        const val ACTION_CANCEL = "com.asadullahalmunib.cliphaven.action.CANCEL"

        const val EXTRA_JOB_ID = "extra_job_id"
        const val EXTRA_TITLE = "extra_title"
        const val EXTRA_DETAIL = "extra_detail"
        const val EXTRA_SUBTEXT = "extra_subtext"
        const val EXTRA_THUMB_URL = "extra_thumb_url"
        const val EXTRA_PERCENT = "extra_percent"
        const val EXTRA_INDETERMINATE = "extra_indeterminate"

        private val BRAND_COLOR = 0xFF8B5CF6.toInt()
        private val COMPLETE_COLOR = 0xFF16A34A.toInt()
        private const val MIN_UPDATE_INTERVAL_MS = 350L

        @Volatile
        private var instance: DownloadForegroundService? = null

        @Volatile
        var onCancelRequested: ((String) -> Unit)? = null

        @Volatile
        private var lastUpdateMs: Long = 0L

        @Volatile
        private var lastStageSubText: String = ""

        fun start(context: Context, jobId: String, title: String, detail: String, thumbUrl: String = "") {
            try {
                lastUpdateMs = 0L
                lastStageSubText = ""
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
                nm?.cancel(COMPLETE_NOTIFICATION_ID)
                val intent = Intent(context, DownloadForegroundService::class.java).apply {
                    action = ACTION_START
                    putExtra(EXTRA_JOB_ID, jobId)
                    putExtra(EXTRA_TITLE, title)
                    putExtra(EXTRA_DETAIL, detail)
                    putExtra(EXTRA_SUBTEXT, "Starting")
                    putExtra(EXTRA_THUMB_URL, thumbUrl)
                    putExtra(EXTRA_PERCENT, 0)
                    putExtra(EXTRA_INDETERMINATE, true)
                }
                ContextCompat.startForegroundService(context, intent)
            } catch (_: Throwable) {
            }
        }

        fun update(
            context: Context,
            jobId: String,
            title: String,
            detail: String,
            subText: String,
            percent: Int,
            indeterminate: Boolean
        ) {
            try {
                val now = System.currentTimeMillis()
                val stageChanged = subText != lastStageSubText
                if (!stageChanged && percent in 1..99 && (now - lastUpdateMs) < MIN_UPDATE_INTERVAL_MS) {
                    return
                }
                lastUpdateMs = now
                lastStageSubText = subText
                instance?.updateNotification(jobId, title, detail, subText, percent, indeterminate)
            } catch (_: Throwable) {
            }
        }

        fun showCompleted(context: Context, videoTitle: String, detailText: String) {
            try {
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    val channel = NotificationChannel(
                        CHANNEL_ID,
                        "ClipHaven Downloads",
                        NotificationManager.IMPORTANCE_LOW
                    ).apply {
                        description = "Shows live download and video conversion progress"
                        setShowBadge(true)
                    }
                    nm.createNotificationChannel(channel)
                }
                val openIntent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                }
                val pendingFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
                } else {
                    PendingIntent.FLAG_UPDATE_CURRENT
                }
                val contentIntent = PendingIntent.getActivity(context, 0, openIntent, pendingFlags)
                val largeBmp = instance?.currentLargeIcon
                    ?: try { BitmapFactory.decodeResource(context.resources, R.mipmap.ic_launcher) } catch (_: Throwable) { null }

                val cleanTitle = videoTitle.ifEmpty { "Media saved" }
                val notif = NotificationCompat.Builder(context, CHANNEL_ID)
                    .setSmallIcon(R.drawable.ic_stat_cliphaven)
                    .setColor(COMPLETE_COLOR)
                    .setContentTitle("Download complete!")
                    .setContentText(cleanTitle)
                    .setSubText("Completed")
                    .setStyle(NotificationCompat.BigTextStyle().bigText("$cleanTitle\n$detailText"))
                    .setLargeIcon(largeBmp)
                    .setContentIntent(contentIntent)
                    .setOngoing(false)
                    .setAutoCancel(true)
                    .setOnlyAlertOnce(false)
                    .setProgress(0, 0, false)
                    .build()

                nm.notify(COMPLETE_NOTIFICATION_ID, notif)
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
    @Volatile
    private var currentJobId: String = ""
    @Volatile
    private var currentTitle: String = "ClipHaven"
    @Volatile
    private var currentDetail: String = "Downloading media…"
    @Volatile
    private var currentSubText: String = ""
    @Volatile
    private var currentPercent: Int = 0
    @Volatile
    private var currentIndeterminate: Boolean = true
    @Volatile
    var currentLargeIcon: Bitmap? = null
        private set

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

    private fun loadThumbnailAsync(thumbUrl: String, forJobId: String) {
        val fallbackLogo = try {
            BitmapFactory.decodeResource(resources, R.mipmap.ic_launcher)
        } catch (_: Throwable) {
            null
        }
        currentLargeIcon = fallbackLogo
        if (thumbUrl.isBlank() || !thumbUrl.startsWith("https://")) return

        thread {
            var conn: HttpURLConnection? = null
            try {
                conn = (URL(thumbUrl).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 3500
                    readTimeout = 3500
                    requestMethod = "GET"
                    setRequestProperty("User-Agent", "Mozilla/5.0")
                }
                if (conn.responseCode == 200) {
                    val bytes = conn.inputStream.use { it.readBytes() }
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    if (bmp != null && currentJobId == forJobId) {
                        currentLargeIcon = bmp
                        updateNotification(
                            currentJobId,
                            currentTitle,
                            currentDetail,
                            currentSubText,
                            currentPercent,
                            currentIndeterminate
                        )
                    }
                }
            } catch (_: Throwable) {
            } finally {
                try { conn?.disconnect() } catch (_: Throwable) {}
            }
        }
    }

    private fun buildNotification(
        jobId: String,
        title: String,
        detail: String,
        subText: String,
        percent: Int,
        indeterminate: Boolean
    ): Notification {
        val pendingFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }

        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, openIntent, pendingFlags)

        val cancelIntent = Intent(this, DownloadForegroundService::class.java).apply {
            action = ACTION_CANCEL
            putExtra(EXTRA_JOB_ID, jobId)
        }
        val cancelPendingIntent = PendingIntent.getService(this, 1, cancelIntent, pendingFlags)

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_cliphaven)
            .setColor(BRAND_COLOR)
            .setContentTitle(title.ifEmpty { "ClipHaven Downloading…" })
            .setContentText(detail)
            .setStyle(NotificationCompat.BigTextStyle().bigText(detail))
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(0, "✕ Cancel", cancelPendingIntent)

        if (subText.isNotEmpty()) {
            builder.setSubText(subText)
        }
        currentLargeIcon?.let { builder.setLargeIcon(it) }

        if (indeterminate) {
            builder.setProgress(100, 0, true)
        } else {
            builder.setProgress(100, percent.coerceIn(0, 100), false)
        }

        return builder.build()
    }

    fun updateNotification(
        jobId: String,
        title: String,
        detail: String,
        subText: String,
        percent: Int,
        indeterminate: Boolean
    ) {
        try {
            if (jobId.isNotEmpty()) currentJobId = jobId
            currentTitle = title
            currentDetail = detail
            currentSubText = subText
            currentPercent = percent
            currentIndeterminate = indeterminate
            val notif = buildNotification(currentJobId, title, detail, subText, percent, indeterminate)
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
        if (action == ACTION_CANCEL) {
            val cancelId = intent?.getStringExtra(EXTRA_JOB_ID).orEmpty().ifEmpty { currentJobId }
            if (cancelId.isNotEmpty()) {
                try {
                    onCancelRequested?.invoke(cancelId)
                } catch (_: Throwable) {
                }
            }
            stopForegroundAndSelf()
            return START_NOT_STICKY
        }

        acquireWakeLock()
        val jobId = intent?.getStringExtra(EXTRA_JOB_ID) ?: ""
        val title = intent?.getStringExtra(EXTRA_TITLE) ?: "ClipHaven"
        val detail = intent?.getStringExtra(EXTRA_DETAIL) ?: "Preparing download…"
        val subText = intent?.getStringExtra(EXTRA_SUBTEXT) ?: "Starting"
        val thumbUrl = intent?.getStringExtra(EXTRA_THUMB_URL) ?: ""
        val percent = intent?.getIntExtra(EXTRA_PERCENT, 0) ?: 0
        val indeterminate = intent?.getBooleanExtra(EXTRA_INDETERMINATE, true) ?: true

        currentJobId = jobId
        currentTitle = title
        currentDetail = detail
        currentSubText = subText
        currentPercent = percent
        currentIndeterminate = indeterminate
        loadThumbnailAsync(thumbUrl, jobId)

        val notif = buildNotification(jobId, title, detail, subText, percent, indeterminate)
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
