package com.asadullah.cliphaven

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.LinkedHashMap
import java.util.Locale
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.math.roundToLong

class MainActivity : AppCompatActivity() {

    companion object {
        private const val REQ_STORAGE_PERMISSION = 1001
        private const val REQ_OPEN_DOCUMENT_TREE = 1002
        private const val MAX_JOBS = 40
        private const val PREFS_NAME = "cliphaven_engine_prefs"
        private const val KEY_YTDLP_UPDATED_AT = "ytdlp_updated_at_v312"
        private const val UPDATE_INTERVAL_MS = 12L * 3600L * 1000L
        private const val SUB_SHIFT_MARKER = "\u2060"

        private val SUB_TS_LINE_REGEX = Regex("""((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})(.*)""")
        private val SUB_INLINE_TS_REGEX = Regex("""<((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})>""")

        private val ALLOWED_DOMAINS = setOf(
            "youtube.com", "youtu.be", "youtube-nocookie.com", "facebook.com", "fb.watch", "fb.com", "fb.gg",
            "instagram.com", "instagr.am", "threads.net", "threads.com", "tiktok.com", "twitter.com", "x.com", "t.co",
            "reddit.com", "redd.it", "vimeo.com", "dailymotion.com", "dai.ly", "twitch.tv",
            "pinterest.com", "pin.it", "soundcloud.com", "snd.sc"
        )
        private val VALID_FORMATS = setOf("mp4", "mkv", "webm", "mp3", "m4a", "wav")
        private val VALID_QUALITIES = setOf("best", "2160", "1440", "1080", "720", "480", "360")
        private val SUB_OR_THUMB_EXTS = setOf("vtt", "srt", "ass", "ssa", "ttml", "srv1", "srv2", "srv3", "json3", "webp", "jpg", "jpeg", "png", "part", "ytdl", "temp", "tmp")
        private val SUB_TEXT_EXTS = setOf("vtt", "srt")
    }

    private var webView: WebView? = null
    private val jobsLock = Any()
    private val updateLock = Any()
    private val jobs = LinkedHashMap<String, JSONObject>()

    private val initLatch = CountDownLatch(1)
    @Volatile
    private var isEngineReady = false
    @Volatile
    private var initErrorMsg: String? = null

    @Volatile
    private var folderTreeLatch: CountDownLatch? = null
    @Volatile
    private var folderTreeResult: String? = null

    private val downloadsRootDir: File
        get() = try {
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                ?: getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                ?: filesDir
        } catch (_: Throwable) {
            filesDir
        }

    private val defaultDownloadDir: File
        get() = try {
            val dir = File(downloadsRootDir, "ClipHaven")
            dir.mkdirs()
            dir
        } catch (_: Throwable) {
            filesDir
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 1. Initialize WebView and set content view FIRST so the UI is always attached immediately
        val wv = WebView(this)
        webView = wv
        setContentView(wv)

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            @Suppress("DEPRECATION")
            allowUniversalAccessFromFileURLs = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }
        wv.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                handleIncomingShareIntent(intent)
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val u = request?.url ?: return false
                if (u.scheme == "http" || u.scheme == "https") {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, u))
                    } catch (_: Throwable) {
                    }
                    return true
                }
                return false
            }
        }
        wv.webChromeClient = WebChromeClient()
        wv.addJavascriptInterface(ClipHavenBridge(), "ClipHavenAndroid")
        wv.loadUrl("file:///android_asset/index.html")

        // 2. Unpack embedded Python/yt-dlp & FFmpeg in background and ensure yt-dlp is updated before first command
        thread {
            try {
                initEngines()
            } catch (_: Throwable) {
            } finally {
                initLatch.countDown()
            }
        }

        // 3. Request legacy storage permission after UI is mounted
        wv.post {
            requestLegacyStoragePermissionIfNeeded()
        }
    }

    @Synchronized
    private fun initEngines(): Boolean {
        if (isEngineReady) return true
        return try {
            YoutubeDL.getInstance().init(applicationContext)
            FFmpeg.getInstance().init(applicationContext)

            val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val lastUpdated = prefs.getLong(KEY_YTDLP_UPDATED_AT, 0L)
            val now = System.currentTimeMillis()
            if (lastUpdated == 0L) {
                // First run after install/upgrade: update yt-dlp synchronously before releasing initLatch
                // so the very first YouTube preview/download uses the latest yt-dlp extractor without race conditions.
                syncUpdateYtDlp(YoutubeDL.UpdateChannel.STABLE)
            } else if (now - lastUpdated > UPDATE_INTERVAL_MS) {
                thread {
                    syncUpdateYtDlp(YoutubeDL.UpdateChannel.STABLE)
                }
            }

            isEngineReady = true
            initErrorMsg = null
            true
        } catch (t: Throwable) {
            initErrorMsg = t.message ?: "Failed to initialize embedded downloader engine."
            false
        }
    }

    private fun syncUpdateYtDlp(channel: YoutubeDL.UpdateChannel): Boolean {
        synchronized(updateLock) {
            return try {
                YoutubeDL.getInstance().updateYoutubeDL(applicationContext, channel)
                getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .putLong(KEY_YTDLP_UPDATED_AT, System.currentTimeMillis())
                    .apply()
                true
            } catch (_: Throwable) {
                false
            }
        }
    }

    private fun isYouTubeClientBlockError(msg: String?): Boolean {
        if (msg.isNullOrBlank()) return false
        val m = msg.lowercase()
        return m.contains("precondition check failed") ||
            m.contains("please sign in") ||
            m.contains("sign in to confirm") ||
            m.contains("http error 400") ||
            m.contains("http error 403") ||
            m.contains("nsig extraction failed")
    }

    private fun ensureEnginesInitialized() {
        if (!isEngineReady) {
            try {
                initLatch.await(60, TimeUnit.SECONDS)
            } catch (_: Throwable) {
            }
            if (!isEngineReady && !initEngines()) {
                throw IllegalStateException(initErrorMsg ?: "Downloader engine is still initializing. Please try again in a moment.")
            }
        }
    }

    private fun requestLegacyStoragePermissionIfNeeded() {
        try {
            if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.Q) {
                val needed = mutableListOf<String>()
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    needed.add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                }
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    needed.add(Manifest.permission.READ_EXTERNAL_STORAGE)
                }
                if (needed.isNotEmpty()) {
                    ActivityCompat.requestPermissions(this, needed.toTypedArray(), REQ_STORAGE_PERMISSION)
                }
            }
        } catch (_: Throwable) {
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        if (intent != null) {
            setIntent(intent)
            handleIncomingShareIntent(intent)
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_OPEN_DOCUMENT_TREE) {
            try {
                if (resultCode == Activity.RESULT_OK && data?.data != null) {
                    folderTreeResult = resolveTreeUriToPath(data.data!!)
                }
            } catch (_: Throwable) {
            } finally {
                folderTreeLatch?.countDown()
            }
        }
    }

    private fun resolveTreeUriToPath(treeUri: Uri): String {
        return try {
            val docId = DocumentsContract.getTreeDocumentId(treeUri)
            val parts = docId.split(":", limit = 2)
            val type = parts.getOrNull(0) ?: ""
            val rel = parts.getOrNull(1)?.trim('/') ?: ""
            when {
                type.equals("primary", ignoreCase = true) -> {
                    val base = Environment.getExternalStorageDirectory()
                    if (rel.isEmpty()) base.absolutePath else File(base, rel).absolutePath
                }
                docId.startsWith("raw:") -> docId.removePrefix("raw:")
                rel.isNotEmpty() -> File(downloadsRootDir, rel).absolutePath
                else -> defaultDownloadDir.absolutePath
            }
        } catch (_: Throwable) {
            defaultDownloadDir.absolutePath
        }
    }

    private fun handleIncomingShareIntent(intent: Intent?) {
        try {
            if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
                val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
                val cleanUrl = extractUrl(sharedText)
                if (cleanUrl.isEmpty()) return
                val escaped = JSONObject.quote(cleanUrl)
                val wv = webView ?: return
                wv.post {
                    wv.evaluateJavascript(
                        "if(document.getElementById('url')){document.getElementById('url').value=$escaped;if(typeof syncClearBtn==='function')syncClearBtn();triggerPreview();}",
                        null
                    )
                }
            }
        } catch (_: Throwable) {
        }
    }

    private fun isAllowedHost(host: String?): Boolean {
        val h = (host ?: "").lowercase().trimEnd('.')
        if (h.isEmpty()) return false
        return ALLOWED_DOMAINS.any { d -> h == d || h.endsWith(".$d") }
    }

    private fun extractUrl(raw: String?): String {
        if (raw.isNullOrBlank()) return ""
        val s = raw.trim()
        val httpMatch = Regex("""https?://[^\s<>"']+""", RegexOption.IGNORE_CASE).find(s)
        if (httpMatch != null) {
            val cleaned = httpMatch.value.trimEnd('.', ',', ';', ')', '!', ']', '>')
            return cleaned.replaceFirst(Regex("""^http://""", RegexOption.IGNORE_CASE), "https://")
        }
        val bareMatch = Regex("""(?:www\.)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/[^\s<>"']*""").find(s)
        if (bareMatch != null) {
            val candidate = bareMatch.value.trimEnd('.', ',', ';', ')', '!', ']', '>')
            val hostPart = candidate.substringBefore('/').lowercase()
            if (isAllowedHost(hostPart)) {
                return "https://$candidate"
            }
        }
        return s
    }

    private fun isValidUrl(raw: String?): Boolean {
        val url = extractUrl(raw)
        return try {
            val u = Uri.parse(url)
            u.scheme?.lowercase() == "https" && isAllowedHost(u.host)
        } catch (_: Throwable) {
            false
        }
    }

    private fun formatDisplayFolder(path: String?): String {
        if (path.isNullOrBlank()) return "Download/ClipHaven"
        val p = path.trim()
        val extRoot = try { Environment.getExternalStorageDirectory().absolutePath } catch (_: Throwable) { "/storage/emulated/0" }
        return when {
            p.startsWith("$extRoot/", ignoreCase = true) -> p.substring(extRoot.length + 1)
            p.equals(extRoot, ignoreCase = true) -> "Download/ClipHaven"
            p.startsWith("/storage/emulated/0/", ignoreCase = true) -> p.substring("/storage/emulated/0/".length)
            p.equals("/storage/emulated/0", ignoreCase = true) -> "Download/ClipHaven"
            else -> {
                p.replaceFirst(Regex("""^/(?:storage/emulated/\d+|storage/sdcard\d+|sdcard)/?""", RegexOption.IGNORE_CASE), "")
                    .replaceFirst(Regex("""^Internal Storage/?""", RegexOption.IGNORE_CASE), "")
                    .ifEmpty { "Download/ClipHaven" }
            }
        }
    }

    private fun normalizeAndroidFolder(rawFolder: String?): File {
        return try {
            val rawTrimmed = (rawFolder ?: "").trim()
            val cleanRel = rawTrimmed
                .replaceFirst(Regex("""^/(?:storage/emulated/\d+|storage/sdcard\d+|sdcard)/?""", RegexOption.IGNORE_CASE), "")
                .replaceFirst(Regex("""^Internal Storage/?""", RegexOption.IGNORE_CASE), "")
                .trimStart('/', '\\')

            if (cleanRel.isEmpty() || cleanRel.equals("Downloads", ignoreCase = true) || cleanRel.equals("Download/ClipHaven", ignoreCase = true) || cleanRel.equals("Downloads/ClipHaven", ignoreCase = true)) {
                return defaultDownloadDir
            }
            if (cleanRel.equals("Download", ignoreCase = true)) {
                return downloadsRootDir
            }
            if (cleanRel.startsWith("Downloads/", ignoreCase = true)) {
                val sub = cleanRel.substring("Downloads/".length).trimStart('/', '\\')
                val target = File(downloadsRootDir, sub)
                target.mkdirs()
                return if (target.exists() && target.isDirectory) target else defaultDownloadDir
            }
            if (cleanRel.startsWith("Download/", ignoreCase = true)) {
                val sub = cleanRel.substring("Download/".length).trimStart('/', '\\')
                val target = File(downloadsRootDir, sub)
                target.mkdirs()
                return if (target.exists() && target.isDirectory) target else defaultDownloadDir
            }

            val extRoot = Environment.getExternalStorageDirectory()
            val candidate = if (rawTrimmed.startsWith("/storage/") && !rawTrimmed.startsWith("/storage/emulated/")) {
                File(rawTrimmed)
            } else {
                File(extRoot, cleanRel)
            }
            if (!candidate.exists()) {
                candidate.mkdirs()
            }
            if (candidate.exists() && candidate.isDirectory) candidate else defaultDownloadDir
        } catch (_: Throwable) {
            defaultDownloadDir
        }
    }

    private fun parseTimestamp(ts: String): Int? {
        val s = ts.trim()
        if (s.isEmpty() || !Regex("""^\d{1,3}(:\d{1,2}){0,2}$""").matches(s)) return null
        val parts = s.split(":").map { it.toInt() }
        return when (parts.size) {
            1 -> parts[0]
            2 -> if (parts[1] < 60) parts[0] * 60 + parts[1] else null
            3 -> if (parts[1] < 60 && parts[2] < 60) parts[0] * 3600 + parts[1] * 60 + parts[2] else null
            else -> null
        }
    }

    private fun formatSeconds(sec: Int): String {
        val clean = sec.coerceAtLeast(0)
        val h = clean / 3600
        val m = (clean % 3600) / 60
        val s = clean % 60
        return if (h > 0) String.format(Locale.US, "%02d:%02d:%02d", h, m, s) else String.format(Locale.US, "%02d:%02d", m, s)
    }

    private fun parseSubTimestampMs(ts: String): Long {
        val clean = ts.trim().replace(',', '.')
        val parts = clean.split(":")
        return try {
            when (parts.size) {
                3 -> {
                    val h = parts[0].toLong()
                    val m = parts[1].toLong()
                    val s = parts[2].toDouble()
                    ((h * 3600L + m * 60L + s) * 1000.0).roundToLong()
                }
                2 -> {
                    val m = parts[0].toLong()
                    val s = parts[1].toDouble()
                    ((m * 60L + s) * 1000.0).roundToLong()
                }
                else -> 0L
            }
        } catch (_: Throwable) {
            0L
        }
    }

    private fun formatSubTimestampMs(ms: Long, sep: Char): String {
        val clean = ms.coerceAtLeast(0L)
        val h = clean / 3600000L
        val rem1 = clean % 3600000L
        val m = rem1 / 60000L
        val rem2 = rem1 % 60000L
        val s = rem2 / 1000L
        val millis = rem2 % 1000L
        return String.format(Locale.US, "%02d:%02d:%02d%c%03d", h, m, s, sep, millis)
    }

    private data class SubtitleCue(
        val startMs: Long,
        val endMs: Long,
        val settings: String,
        val payload: MutableList<String>
    )

    private fun trimAndShiftSubtitleText(content: String, startSec: Int, endSec: Int?, isVtt: Boolean): String {
        if (content.isEmpty() || content.contains(SUB_SHIFT_MARKER)) return content
        val startMs = (startSec.coerceAtLeast(0)).toLong() * 1000L
        val endMs = endSec?.let { it.toLong() * 1000L }
        if (startMs == 0L && endMs == null) return content

        val sep = if (isVtt) '.' else ','
        val blocks = content.removePrefix("\uFEFF").trim().split(Regex("""\r?\n\r?\n+"""))
        val headerBlocks = mutableListOf<String>()
        val cueBlocks = mutableListOf<SubtitleCue>()

        for (block in blocks) {
            val lines = block.split("\n").map { it.trimEnd('\r') }
            var tsIdx = -1
            for (i in lines.indices) {
                if (lines[i].contains("-->") && SUB_TS_LINE_REGEX.containsMatchIn(lines[i])) {
                    tsIdx = i
                    break
                }
            }
            if (tsIdx == -1) {
                if (isVtt && cueBlocks.isEmpty() && lines.isNotEmpty() && (
                        lines[0].startsWith("WEBVTT") ||
                            lines[0].startsWith("Kind:") ||
                            lines[0].startsWith("Language:") ||
                            lines[0].startsWith("NOTE") ||
                            lines[0].startsWith("STYLE")
                        )
                ) {
                    headerBlocks.add(lines.joinToString("\n"))
                }
                continue
            }

            val m = SUB_TS_LINE_REGEX.find(lines[tsIdx]) ?: continue
            val cStart = parseSubTimestampMs(m.groupValues[1])
            val cEnd = parseSubTimestampMs(m.groupValues[2])
            val settings = m.groupValues[3]

            if (cEnd <= startMs) continue
            if (endMs != null && cStart >= endMs) continue

            val newStart = (cStart - startMs).coerceAtLeast(0L)
            val clampedEnd = if (endMs != null) cEnd.coerceAtMost(endMs) else cEnd
            val newEnd = clampedEnd - startMs
            if (newEnd <= newStart) continue

            val payload = lines.drop(tsIdx + 1)
                .filter { it.isNotBlank() }
                .map { ln ->
                    SUB_INLINE_TS_REGEX.replace(ln) { match ->
                        val rawMs = parseSubTimestampMs(match.groupValues[1])
                        var shifted = (rawMs - startMs).coerceAtLeast(0L)
                        if (endMs != null) {
                            shifted = shifted.coerceAtMost((endMs - startMs).coerceAtLeast(0L))
                        }
                        "<${formatSubTimestampMs(shifted, sep)}>"
                    }
                }
                .toMutableList()
            if (payload.isEmpty()) continue
            cueBlocks.add(SubtitleCue(newStart, newEnd, settings, payload))
        }

        if (cueBlocks.isEmpty()) {
            cueBlocks.add(SubtitleCue(0L, 100L, "", mutableListOf("\u200B")))
        }

        val firstPayload = cueBlocks[0].payload
        firstPayload[firstPayload.lastIndex] = firstPayload.last() + SUB_SHIFT_MARKER

        val outBlocks = mutableListOf<String>()
        if (isVtt) {
            if (headerBlocks.isNotEmpty()) outBlocks.addAll(headerBlocks) else outBlocks.add("WEBVTT")
        }
        for ((index, cue) in cueBlocks.withIndex()) {
            val tsLine = "${formatSubTimestampMs(cue.startMs, sep)} --> ${formatSubTimestampMs(cue.endMs, sep)}${cue.settings}"
            if (isVtt) {
                outBlocks.add(tsLine + "\n" + cue.payload.joinToString("\n"))
            } else {
                outBlocks.add("${index + 1}\n$tsLine\n" + cue.payload.joinToString("\n"))
            }
        }
        return outBlocks.joinToString("\n\n") + "\n"
    }

    private fun hasActiveVideoFileInWorkDir(workDir: File): Boolean {
        return try {
            val files = workDir.listFiles() ?: return false
            files.any { f ->
                if (!f.isFile) return@any false
                val nameLow = f.name.lowercase()
                if (nameLow.endsWith(".tmp") || nameLow.endsWith(".ytdl")) return@any false
                val cleanName = nameLow.replace(Regex("""\.(?:part|temp)(?:-\w+)?$"""), "")
                val ext = cleanName.substringAfterLast('.', "")
                ext in setOf("mp4", "mkv", "webm", "m4a")
            }
        } catch (_: Throwable) {
            false
        }
    }

    private fun syncClipSubtitlesInDir(workDir: File, startSec: Int, endSec: Int?, expectSrt: Boolean) {
        try {
            val files = workDir.listFiles() ?: return
            if (expectSrt && files.any { it.isFile && it.extension.lowercase() == "vtt" }) {
                // Wait until SubtitlesConvertor (before_dl) has finished converting and deleting all .vtt files in workDir
                return
            }
            for (f in files) {
                if (!f.isFile || f.length() <= 0L) continue
                val ext = f.extension.lowercase()
                if (ext !in SUB_TEXT_EXTS || f.name.endsWith(".tmp")) continue
                if (expectSrt && ext != "srt") continue
                val raw = try {
                    f.readText(Charsets.UTF_8)
                } catch (_: Throwable) {
                    continue
                }
                if (raw.contains(SUB_SHIFT_MARKER)) continue
                val shifted = trimAndShiftSubtitleText(raw, startSec, endSec, isVtt = (ext == "vtt"))
                if (shifted == raw) continue
                val tmpFile = File(workDir, "${f.name}.cliphaven.tmp")
                tmpFile.writeText(shifted, Charsets.UTF_8)
                if (!tmpFile.renameTo(f)) {
                    f.writeText(shifted, Charsets.UTF_8)
                    tmpFile.delete()
                }
            }
        } catch (_: Throwable) {
        }
    }

    private fun updateJob(jid: String, updates: Map<String, Any?>) {
        synchronized(jobsLock) {
            val job = jobs[jid] ?: return
            if (job.optString("state") == "Cancelled" && updates["state"] != "Cancelled") {
                return
            }
            for ((k, v) in updates) {
                job.put(k, v)
            }
        }
    }

    private fun getJobSnapshot(jid: String): JSONObject? {
        synchronized(jobsLock) {
            val job = jobs[jid] ?: return null
            return JSONObject(job.toString())
        }
    }

    private fun pruneJobs() {
        synchronized(jobsLock) {
            if (jobs.size <= MAX_JOBS) return
            val doneKeys = jobs.entries
                .filter { it.value.optString("state") in setOf("Complete", "Error", "Cancelled") }
                .map { it.key }
            val toRemove = (jobs.size - MAX_JOBS).coerceAtLeast(0)
            doneKeys.take(toRemove).forEach { jobs.remove(it) }
        }
    }

    private fun showFolderPickerDialog(currentFolder: String): String? {
        val latch = CountDownLatch(1)
        var selectedPath: String? = null
        val dlRoot = downloadsRootDir
        val presetPaths = arrayOf(
            File(dlRoot, "ClipHaven").absolutePath,
            File(dlRoot, "ClipHaven/Videos").absolutePath,
            File(dlRoot, "ClipHaven/Audio").absolutePath,
            dlRoot.absolutePath
        )
        val labels = arrayOf(
            "📁 Download/ClipHaven (Default)",
            "🎬 Download/ClipHaven/Videos",
            "🎵 Download/ClipHaven/Audio",
            "📥 Download (Root)",
            "📂 Browse Device Folders…",
            "✏️ Custom Subfolder…"
        )
        runOnUiThread {
            try {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Select Save Folder")
                    .setItems(labels) { _, which ->
                        when {
                            which < 4 -> {
                                selectedPath = formatDisplayFolder(presetPaths[which])
                                latch.countDown()
                            }
                            which == 4 -> {
                                try {
                                    val treeLatch = CountDownLatch(1)
                                    folderTreeLatch = treeLatch
                                    folderTreeResult = null
                                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                                    }
                                    @Suppress("DEPRECATION")
                                    startActivityForResult(intent, REQ_OPEN_DOCUMENT_TREE)
                                    thread {
                                        try {
                                            treeLatch.await(120, TimeUnit.SECONDS)
                                            selectedPath = folderTreeResult?.let { formatDisplayFolder(it) }
                                        } catch (_: Throwable) {
                                        } finally {
                                            latch.countDown()
                                        }
                                    }
                                } catch (_: Throwable) {
                                    latch.countDown()
                                }
                            }
                            else -> {
                                val relDefault = formatDisplayFolder(currentFolder).ifEmpty { "Download/ClipHaven" }
                                val input = EditText(this@MainActivity).apply {
                                    hint = "e.g. Download/MyClips or C programing/Web"
                                    setText(relDefault)
                                }
                                AlertDialog.Builder(this@MainActivity)
                                    .setTitle("Enter Folder Path")
                                    .setView(input)
                                    .setPositiveButton("OK") { _, _ ->
                                        val entered = input.text.toString().trim().trimStart('/', '\\')
                                        selectedPath = if (entered.isNotEmpty()) {
                                            entered
                                        } else {
                                            "Download/ClipHaven"
                                        }
                                        latch.countDown()
                                    }
                                    .setNegativeButton("Cancel") { _, _ -> latch.countDown() }
                                    .setOnCancelListener { latch.countDown() }
                                    .show()
                            }
                        }
                    }
                    .setNegativeButton("Cancel") { _, _ -> latch.countDown() }
                    .setOnCancelListener { latch.countDown() }
                    .show()
            } catch (_: Throwable) {
                latch.countDown()
            }
        }
        try {
            latch.await(120, TimeUnit.SECONDS)
        } catch (_: Throwable) {
        }
        return selectedPath
    }

    private fun exportStagedFilesToTargetDir(workDir: File, outDir: File): List<File> {
        val exported = mutableListOf<File>()
        val candidates = workDir.listFiles()?.filter { f ->
            f.isFile && f.length() > 0 && f.extension.lowercase() !in SUB_OR_THUMB_EXTS && !f.name.contains(".part")
        } ?: emptyList()

        try {
            outDir.mkdirs()
        } catch (_: Throwable) {
        }

        for (src in candidates) {
            val destFile = File(outDir, src.name)
            var copiedDirect = false
            try {
                if (destFile.exists()) destFile.delete()
                src.copyTo(destFile, overwrite = true)
                if (destFile.isFile && destFile.length() > 0) {
                    exported.add(destFile)
                    copiedDirect = true
                }
            } catch (_: Throwable) {
            }

            if (!copiedDirect && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                try {
                    val relSubpath = outDir.absolutePath
                        .removePrefix(Environment.getExternalStorageDirectory().absolutePath)
                        .trimStart('/', '\\')
                        .ifEmpty { Environment.DIRECTORY_DOWNLOADS + "/ClipHaven" }
                    val values = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, src.name)
                        put(MediaStore.MediaColumns.RELATIVE_PATH, relSubpath)
                        put(MediaStore.MediaColumns.IS_PENDING, 1)
                    }
                    val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    if (uri != null) {
                        contentResolver.openOutputStream(uri)?.use { outStream ->
                            src.inputStream().use { inStream -> inStream.copyTo(outStream) }
                        }
                        values.clear()
                        values.put(MediaStore.MediaColumns.IS_PENDING, 0)
                        contentResolver.update(uri, values, null, null)
                        exported.add(destFile)
                    }
                } catch (_: Throwable) {
                }
            }
        }
        return exported
    }

    private fun buildInfoRequest(url: String, hasVideoAndList: Boolean, useFallbackClient: Boolean): YoutubeDLRequest {
        return YoutubeDLRequest(url).apply {
            addOption("--dump-single-json")
            if (hasVideoAndList) {
                addOption("--no-playlist")
            } else {
                addOption("--flat-playlist")
                addOption("--playlist-end", "50")
            }
            if (useFallbackClient) {
                addOption("--extractor-args", "youtube:player_client=default,ios,mweb")
            }
            addOption("--no-check-certificates")
            addOption("--no-warnings")
        }
    }

    inner class ClipHavenBridge {
        @JavascriptInterface
        fun requestAsync(reqId: String, path: String, method: String, bodyRaw: String) {
            thread {
                try {
                    val resJson = request(path, method, bodyRaw)
                    val qId = JSONObject.quote(reqId)
                    val wv = webView ?: return@thread
                    wv.post {
                        wv.evaluateJavascript(
                            "window.__onAndroidApiResult && window.__onAndroidApiResult($qId, $resJson);",
                            null
                        )
                    }
                } catch (_: Throwable) {
                }
            }
        }

        @JavascriptInterface
        fun request(path: String, method: String, bodyRaw: String): String {
            return try {
                val uri = Uri.parse("http://127.0.0.1$path")
                val cleanPath = uri.path ?: path
                val body = try {
                    JSONObject(if (bodyRaw.isBlank()) "{}" else bodyRaw)
                } catch (_: Throwable) {
                    JSONObject()
                }

                when (cleanPath) {
                    "/api/config" -> {
                        val arr = JSONArray()
                        synchronized(jobsLock) {
                            jobs.values.toList().takeLast(10).forEach { arr.put(JSONObject(it.toString())) }
                        }
                        JSONObject()
                            .put("ok", true)
                            .put("version", "3.1.2")
                            .put("author", "Md Asadullah Al Munib")
                            .put("repo_url", "https://github.com/AsadullahAlMunib/ClipHaven/")
                            .put("default_folder", formatDisplayFolder(defaultDownloadDir.absolutePath))
                            .put("raw_folder", defaultDownloadDir.absolutePath)
                            .put("ffmpeg", true)
                            .put("jobs", arr)
                            .toString()
                    }
                    "/api/ffmpeg" -> JSONObject().put("ok", true).put("available", true).toString()
                    "/api/status" -> {
                        val id = uri.getQueryParameter("id") ?: ""
                        val j = getJobSnapshot(id)
                        if (j != null) {
                            j.put("ok", true).toString()
                        } else {
                            JSONObject().put("ok", false).put("error", "Download job not found.").toString()
                        }
                    }
                    "/api/info" -> {
                        val url = extractUrl(body.optString("url", ""))
                        if (!isValidUrl(url)) {
                            return JSONObject().put("ok", false).put("error", "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.).").toString()
                        }
                        ensureEnginesInitialized()
                        val parsedUri = Uri.parse(url)
                        val hasVideoAndList = !parsedUri.getQueryParameter("list").isNullOrEmpty() &&
                            (!parsedUri.getQueryParameter("v").isNullOrEmpty() || parsedUri.host?.lowercase() == "youtu.be")

                        val res = try {
                            YoutubeDL.getInstance().execute(buildInfoRequest(url, hasVideoAndList, false))
                        } catch (t: Throwable) {
                            if (isYouTubeClientBlockError(t.message)) {
                                syncUpdateYtDlp(YoutubeDL.UpdateChannel.NIGHTLY)
                            }
                            YoutubeDL.getInstance().execute(buildInfoRequest(url, hasVideoAndList, true))
                        }

                        val rawOut = res.out.trim()
                        val jsonLine = rawOut.lineSequence().lastOrNull { it.trim().startsWith("{") } ?: rawOut
                        val data = JSONObject(jsonLine)
                        val entries = data.optJSONArray("entries")
                        val isPlaylist = hasVideoAndList || data.optString("_type") == "playlist" || (entries != null && entries.length() > 0)
                        val dur = data.optDouble("duration", 0.0)
                        var thumb = data.optString("thumbnail", "")
                        if (thumb.isEmpty()) {
                            val thumbs = data.optJSONArray("thumbnails")
                            if (thumbs != null && thumbs.length() > 0) {
                                thumb = thumbs.optJSONObject(thumbs.length() - 1)?.optString("url", "") ?: ""
                            }
                        }
                        val plCount = if (data.optInt("playlist_count", 0) > 0) {
                            data.optInt("playlist_count")
                        } else if (entries != null && entries.length() > 0) {
                            entries.length()
                        } else if (hasVideoAndList) {
                            2
                        } else {
                            1
                        }
                        val infoObj = JSONObject()
                            .put("title", data.optString("title", "Video ready to download"))
                            .put("uploader", data.optString("uploader", data.optString("channel", "Video")))
                            .put("duration", if (dur > 0) formatSeconds(dur.toInt()) else "")
                            .put("duration_seconds", if (dur > 0) dur.toInt() else 0)
                            .put("thumbnail", thumb)
                            .put("is_playlist", isPlaylist)
                            .put("playlist_count", plCount)
                            .put("webpage_url", data.optString("webpage_url", url))
                        JSONObject().put("ok", true).put("info", infoObj).toString()
                    }
                    "/api/download" -> startDownloadJob(body)
                    "/api/cancel" -> {
                        val id = body.optString("id", "").trim()
                        updateJob(
                            id,
                            mapOf(
                                "state" to "Cancelled",
                                "title" to "Download cancelled",
                                "detail" to "Download cancelled and temporary files cleaned up.",
                                "stage" to "Cancelled",
                                "percent" to 0,
                                "indeterminate" to false,
                                "speed" to "",
                                "eta" to ""
                            )
                        )
                        try {
                            YoutubeDL.getInstance().destroyProcessById(id)
                        } catch (_: Throwable) {
                        }
                        JSONObject().put("ok", true).toString()
                    }
                    "/api/open-folder" -> {
                        val reqPath = body.optString("path", "").trim()
                        val jid = body.optString("id", "").trim()
                        val resolvedTarget = when {
                            reqPath.isNotEmpty() -> reqPath
                            jid.isNotEmpty() -> getJobSnapshot(jid)?.optString("file_path") ?: defaultDownloadDir.absolutePath
                            else -> defaultDownloadDir.absolutePath
                        }
                        runOnUiThread {
                            try {
                                startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            } catch (_: Throwable) {
                            }
                            Toast.makeText(this@MainActivity, "Saved in: ${formatDisplayFolder(resolvedTarget)}", Toast.LENGTH_LONG).show()
                        }
                        JSONObject().put("ok", true).toString()
                    }
                    "/api/pick-folder" -> {
                        val current = body.optString("current", defaultDownloadDir.absolutePath)
                        val chosen = showFolderPickerDialog(current)
                        if (chosen.isNullOrBlank()) {
                            JSONObject().put("ok", true).put("cancelled", true).put("folder", "").toString()
                        } else {
                            val dir = normalizeAndroidFolder(chosen)
                            JSONObject()
                                .put("ok", true)
                                .put("cancelled", false)
                                .put("folder", formatDisplayFolder(dir.absolutePath))
                                .put("raw_folder", dir.absolutePath)
                                .toString()
                        }
                    }
                    else -> JSONObject().put("ok", false).put("error", "Not found.").toString()
                }
            } catch (t: Throwable) {
                JSONObject().put("ok", false).put("error", t.message ?: "Request failed").toString()
            }
        }

        private fun createDownloadRequest(
            url: String,
            allowPlaylist: Boolean,
            fmt: String,
            quality: String,
            isClipJob: Boolean,
            sSec: Int?,
            eSec: Int?,
            clipDuration: Int,
            startTime: String,
            endTime: String,
            subtitles: Boolean,
            embedThumb: Boolean,
            workDir: File,
            useFallbackClient: Boolean
        ): YoutubeDLRequest {
            return YoutubeDLRequest(url).apply {
                addOption(if (allowPlaylist) "--yes-playlist" else "--no-playlist")
                if (allowPlaylist) addOption("--ignore-errors")
                if (useFallbackClient) {
                    addOption("--extractor-args", "youtube:player_client=default,ios,mweb")
                }
                addOption("--newline")
                addOption("--progress")
                addOption("--no-mtime")
                addOption("--no-check-certificates")
                addOption("--windows-filenames")
                if (fmt in setOf("mp3", "m4a", "wav")) {
                    addOption("-x")
                    addOption("--audio-format", fmt)
                    addOption("--audio-quality", "0")
                } else {
                    val fExpr = if (fmt == "mp4") {
                        if (quality == "best") {
                            "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b[ext=mp4]/b"
                        } else {
                            "bv*[ext=mp4][height<=$quality]+ba[ext=m4a]/bv*[height<=$quality]+ba/b[height<=$quality]/b"
                        }
                    } else {
                        if (quality == "best") "bv*+ba/b" else "bv*[height<=$quality]+ba/b[height<=$quality]/b"
                    }
                    addOption("--format", fExpr)
                    addOption("--merge-output-format", fmt)
                }
                var clipSuffix = ""
                if (isClipJob) {
                    val endPart = eSec?.toString() ?: "inf"
                    addOption("--download-sections", "*${sSec ?: 0}-$endPart")
                    addOption("--force-keyframes-at-cuts")
                    addOption("--no-embed-chapters")
                    addOption("--downloader-args", "ffmpeg:-stats -v warning")
                    clipSuffix = " [clip ${(startTime.ifEmpty { "0" }).replace(":", "-")}_to_${(endTime.ifEmpty { "end" }).replace(":", "-")}]"
                }
                if (subtitles && fmt in setOf("mp4", "mkv", "webm")) {
                    addOption("--write-subs")
                    addOption("--write-auto-subs")
                    addOption("--sub-langs", "en,bn,en-orig")
                    addOption("--compat-options", "no-keep-subs")
                    addOption("--ignore-errors")
                    if (fmt in setOf("mp4", "mkv")) {
                        addOption("--convert-subs", "srt")
                    }
                    if (isClipJob && clipDuration > 0) {
                        addOption("--postprocessor-args", "EmbedSubtitle+ffmpeg_o:-t $clipDuration")
                    }
                    addOption("--embed-subs")
                }
                if (embedThumb && fmt in setOf("mp4", "mkv", "mp3", "m4a")) {
                    addOption("--convert-thumbnails", "jpg")
                    addOption("--embed-thumbnail")
                }
                addOption("-o", File(workDir, "%(title).160B [%(id)s]$clipSuffix.%(ext)s").absolutePath)
            }
        }

        private fun startDownloadJob(body: JSONObject): String {
            val url = extractUrl(body.optString("url", ""))
            if (!isValidUrl(url)) {
                return JSONObject().put("ok", false).put("error", "Enter a valid HTTPS link (YouTube, Facebook, Instagram, TikTok, X, etc.).").toString()
            }
            val folderRaw = body.optString("folder", "").trim()
            val fmt = body.optString("format", "mp4").lowercase().trim()
            val quality = body.optString("quality", "best").trim()
            if (fmt !in VALID_FORMATS || (fmt in setOf("mp4", "mkv", "webm") && quality !in VALID_QUALITIES)) {
                return JSONObject().put("ok", false).put("error", "Choose a valid format and quality.").toString()
            }
            val startTime = body.optString("start_time", "").trim()
            val endTime = body.optString("end_time", "").trim()
            val subtitles = body.optBoolean("subtitles", false)
            val embedThumb = body.optBoolean("embed_thumbnail", false)
            val allowPlaylist = body.optBoolean("allow_playlist", false)
            val titleHint = body.optString("title_hint", "").trim()
            val durationHint = body.optInt("duration_hint", 0)

            val sSec = if (startTime.isNotEmpty()) parseTimestamp(startTime) else 0
            val eSec = if (endTime.isNotEmpty()) parseTimestamp(endTime) else null
            if ((startTime.isNotEmpty() && sSec == null) || (endTime.isNotEmpty() && eSec == null)) {
                return JSONObject().put("ok", false).put("error", "Clip time must be in MM:SS or HH:MM:SS format.").toString()
            }
            if (eSec != null && sSec != null && eSec <= sSec) {
                return JSONObject().put("ok", false).put("error", "End time must be after start time.").toString()
            }
            if (durationHint > 0 && sSec != null && sSec >= durationHint) {
                return JSONObject().put("ok", false).put("error", "Start time exceeds video duration.").toString()
            }

            val isClipJob = (sSec != null && sSec > 0) || eSec != null
            val clipDuration = when {
                eSec != null && sSec != null -> (eSec - sSec).coerceAtLeast(1)
                isClipJob && durationHint > (sSec ?: 0) -> (durationHint - (sSec ?: 0)).coerceAtLeast(1)
                else -> 0
            }

            val outDir = normalizeAndroidFolder(folderRaw)
            val jid = UUID.randomUUID().toString().replace("-", "")
            val initialJob = JSONObject()
                .put("id", jid)
                .put("state", "Downloading")
                .put("title", if (isClipJob) "Preparing clip cutter…" else "Starting download")
                .put("video_title", if (titleHint.isNotEmpty()) titleHint else "ClipHaven download")
                .put("video_title_locked", titleHint.isNotEmpty())
                .put("format", fmt.uppercase())
                .put("quality", if (fmt in setOf("mp3", "m4a", "wav")) "Audio" else if (quality == "best") "Best" else "${quality}p")
                .put("detail", "Connecting to media stream…")
                .put("percent", 0)
                .put("indeterminate", isClipJob)
                .put("speed", "")
                .put("eta", "")
                .put("stage", if (isClipJob) "Cutting clip" else "Preparing")
                .put("playlist_index", 0)
                .put("playlist_total", 0)
                .put("playlist_done", 0)
                .put("playlist_left", 0)
                .put("folder", formatDisplayFolder(outDir.absolutePath))
                .put("file_path", outDir.absolutePath)

            synchronized(jobsLock) {
                jobs[jid] = initialJob
            }

            thread {
                val workDir = File(cacheDir, "dl_$jid").apply { mkdirs() }
                val expectSrtSubs = subtitles && fmt in setOf("mp4", "mkv")
                val subWatcherRunning = AtomicBoolean(true)
                val subSyncLock = Any()
                @Volatile
                var mediaPhaseStarted = false

                fun trySyncSubs() {
                    if (!isClipJob || !subtitles) return
                    if (!mediaPhaseStarted && !hasActiveVideoFileInWorkDir(workDir)) return
                    synchronized(subSyncLock) {
                        syncClipSubtitlesInDir(workDir, sSec ?: 0, eSec, expectSrtSubs)
                    }
                }

                if (isClipJob && subtitles) {
                    thread {
                        while (subWatcherRunning.get()) {
                            try {
                                trySyncSubs()
                                Thread.sleep(80)
                            } catch (_: Throwable) {
                                break
                            }
                        }
                    }
                }

                try {
                    ensureEnginesInitialized()

                    val progressCallback: (Float, Long, String) -> Unit = { progress, etaInSeconds, line ->
                        val cleanLine = line.trim()
                        val updates = mutableMapOf<String, Any?>()

                        val plMatch = Regex("""\[download\] Downloading (?:item|video)\s+(\d+)\s+of\s+(\d+)""", RegexOption.IGNORE_CASE).find(cleanLine)
                        if (plMatch != null) {
                            val idx = plMatch.groupValues[1].toInt()
                            val tot = plMatch.groupValues[2].toInt()
                            mediaPhaseStarted = false
                            updates["playlist_index"] = idx
                            updates["playlist_total"] = tot
                            updates["playlist_done"] = (idx - 1).coerceAtLeast(0)
                            updates["playlist_left"] = (tot - idx).coerceAtLeast(0)
                            updates["percent"] = 0
                            updates["stage"] = "Video $idx/$tot"
                            updates["title"] = "Downloading video $idx of $tot…"
                        }

                        val destMatch = Regex("""\[download\] Destination:\s+(.+)$""").find(cleanLine)
                        if (destMatch != null) {
                            val cand = destMatch.groupValues[1].trim().trim('"')
                            val ext = File(cand).extension.lowercase()
                            if (ext.isNotEmpty() && ext !in SUB_OR_THUMB_EXTS) {
                                mediaPhaseStarted = true
                            }
                        }

                        val speedMatch = Regex("""at\s+([\d.]+\s*\w+/s)""").find(cleanLine)
                        if (speedMatch != null) {
                            updates["speed"] = speedMatch.groupValues[1].trim()
                        }

                        val elapsedMatch = Regex("""\((\d{2}):(\d{2}):(\d{2})\)""").find(cleanLine)
                        val ffMatch = Regex("""time=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)""").find(cleanLine)
                        if (
                            ffMatch != null ||
                            elapsedMatch != null ||
                            cleanLine.contains("Input #0,") ||
                            cleanLine.contains("Output #0,") ||
                            cleanLine.contains("Downloading 1 time ranges") ||
                            cleanLine.contains("[Merger]") ||
                            cleanLine.contains("Merging formats") ||
                            cleanLine.contains("[EmbedSubtitle]")
                        ) {
                            mediaPhaseStarted = true
                        }

                        if (isClipJob && subtitles) {
                            trySyncSubs()
                        }

                        if (progress > 0f) {
                            val pct = progress.coerceIn(0f, 100f)
                            updates["percent"] = pct
                            updates["indeterminate"] = false
                            updates["eta"] = if (etaInSeconds > 0) formatSeconds(etaInSeconds.toInt()) else ""
                            updates["title"] = if (isClipJob) "Cutting & downloading clip (${pct.toInt()}%)" else "Downloading (${pct.toInt()}%)"
                            updates["stage"] = if (isClipJob) "Cutting clip" else "Downloading"
                        } else if (elapsedMatch != null && isClipJob) {
                            val curSec = elapsedMatch.groupValues[1].toInt() * 3600 + elapsedMatch.groupValues[2].toInt() * 60 + elapsedMatch.groupValues[3].toInt()
                            if (clipDuration > 0 && curSec > 0) {
                                val pct = ((curSec.toFloat() / clipDuration.toFloat()) * 100f).coerceIn(1f, 99f)
                                updates["percent"] = pct
                                updates["indeterminate"] = false
                                updates["title"] = "Cutting & downloading clip (${pct.toInt()}%)"
                                updates["stage"] = "Cutting clip"
                            }
                        } else if (ffMatch != null && isClipJob) {
                            val curSec = ffMatch.groupValues[1].toInt() * 3600 + ffMatch.groupValues[2].toInt() * 60 + ffMatch.groupValues[3].toFloat()
                            if (clipDuration > 0 && curSec > 0f) {
                                val pct = ((curSec / clipDuration.toFloat()) * 100f).coerceIn(1f, 99f)
                                updates["percent"] = pct
                                updates["indeterminate"] = false
                                updates["title"] = "Cutting & encoding clip (${pct.toInt()}%)"
                                updates["stage"] = "Cutting clip"
                            }
                        }

                        when {
                            cleanLine.contains("Merging formats") || cleanLine.contains("[Merger]") -> {
                                updates["title"] = "Merging video & audio (almost done)…"
                                updates["stage"] = "Merging"
                                updates["indeterminate"] = true
                            }
                            cleanLine.contains("[ExtractAudio]") -> {
                                updates["title"] = "Converting audio format…"
                                updates["stage"] = "Converting audio"
                                updates["indeterminate"] = true
                            }
                            cleanLine.contains("Writing video subtitles") || cleanLine.contains("[SubtitlesConvertor]") || cleanLine.contains("[EmbedSubtitle]") -> {
                                updates["title"] = "Processing & embedding subtitles (CC)…"
                                updates["stage"] = "Subtitles (CC)"
                                updates["indeterminate"] = true
                            }
                            cleanLine.contains("Downloading video thumbnail") || cleanLine.contains("[ThumbnailsConvertor]") || cleanLine.contains("[EmbedThumbnail]") -> {
                                updates["title"] = "Embedding cover art / thumbnail…"
                                updates["stage"] = "Embedding cover"
                                updates["indeterminate"] = true
                            }
                        }

                        if (cleanLine.isNotEmpty()) updates["detail"] = cleanLine.take(500)
                        updateJob(jid, updates)
                    }

                    val primaryReq = createDownloadRequest(url, allowPlaylist, fmt, quality, isClipJob, sSec, eSec, clipDuration, startTime, endTime, subtitles, embedThumb, workDir, false)
                    try {
                        YoutubeDL.getInstance().execute(primaryReq, jid, progressCallback)
                    } catch (firstErr: Throwable) {
                        val isCancelledNow = getJobSnapshot(jid)?.optString("state") == "Cancelled"
                        val alreadyExported = exportStagedFilesToTargetDir(workDir, outDir)
                        if (!isCancelledNow && alreadyExported.isEmpty() && isYouTubeClientBlockError(firstErr.message)) {
                            mediaPhaseStarted = false
                            updateJob(jid, mapOf("title" to "Updating extractor & retrying…", "detail" to "Syncing latest YouTube extractor…", "indeterminate" to true))
                            syncUpdateYtDlp(YoutubeDL.UpdateChannel.NIGHTLY)
                            val fallbackReq = createDownloadRequest(url, allowPlaylist, fmt, quality, isClipJob, sSec, eSec, clipDuration, startTime, endTime, subtitles, embedThumb, workDir, true)
                            YoutubeDL.getInstance().execute(fallbackReq, jid, progressCallback)
                        } else if (alreadyExported.isEmpty()) {
                            throw firstErr
                        }
                    }

                    subWatcherRunning.set(false)
                    val isCancelled = getJobSnapshot(jid)?.optString("state") == "Cancelled"
                    if (!isCancelled) {
                        val exportedFiles = exportStagedFilesToTargetDir(workDir, outDir)
                        if (exportedFiles.isEmpty()) {
                            throw IllegalStateException("Download finished, but output media file could not be saved.")
                        }
                        val scanPaths = exportedFiles.map { it.absolutePath }.toTypedArray()
                        MediaScannerConnection.scanFile(applicationContext, scanPaths, null, null)

                        val firstSaved = exportedFiles.first()
                        val cleanTitle = firstSaved.name.replace(Regex("""\s*\[[A-Za-z0-9_-]{3,}\](?:\s*\[clip [^\]]+\])?\.[A-Za-z0-9]+$"""), "")
                        val snapshot = getJobSnapshot(jid)
                        val plTot = snapshot?.optInt("playlist_total", 0) ?: 0
                        val finalUpdates = mutableMapOf<String, Any?>(
                            "state" to "Complete",
                            "title" to "Download complete!",
                            "detail" to if (exportedFiles.size > 1) "Saved ${exportedFiles.size} files to ${formatDisplayFolder(outDir.absolutePath)}" else "Saved: ${firstSaved.name}",
                            "percent" to 100,
                            "indeterminate" to false,
                            "speed" to "",
                            "eta" to "",
                            "stage" to "Complete",
                            "folder" to formatDisplayFolder(outDir.absolutePath),
                            "file_path" to if (exportedFiles.size > 1) outDir.absolutePath else firstSaved.absolutePath
                        )
                        if (cleanTitle.isNotEmpty() && exportedFiles.size == 1 && (!allowPlaylist || snapshot?.optBoolean("video_title_locked") != true)) {
                            finalUpdates["video_title"] = cleanTitle
                        }
                        if (plTot > 1) {
                            finalUpdates["playlist_index"] = plTot
                            finalUpdates["playlist_done"] = plTot
                            finalUpdates["playlist_left"] = 0
                        }
                        updateJob(jid, finalUpdates)
                    }
                } catch (t: Throwable) {
                    subWatcherRunning.set(false)
                    val snapshot = getJobSnapshot(jid)
                    if (snapshot?.optString("state") != "Cancelled") {
                        val exportedFiles = exportStagedFilesToTargetDir(workDir, outDir)
                        if (exportedFiles.isNotEmpty()) {
                            val scanPaths = exportedFiles.map { it.absolutePath }.toTypedArray()
                            MediaScannerConnection.scanFile(applicationContext, scanPaths, null, null)
                            val firstSaved = exportedFiles.first()
                            updateJob(
                                jid,
                                mapOf(
                                    "state" to "Complete",
                                    "title" to "Download complete!",
                                    "detail" to "Saved: ${firstSaved.name}",
                                    "percent" to 100,
                                    "indeterminate" to false,
                                    "speed" to "",
                                    "eta" to "",
                                    "stage" to "Complete",
                                    "folder" to formatDisplayFolder(outDir.absolutePath),
                                    "file_path" to firstSaved.absolutePath
                                )
                            )
                        } else {
                            updateJob(
                                jid,
                                mapOf(
                                    "state" to "Error",
                                    "title" to "Download failed",
                                    "detail" to (t.message ?: "Download failed").take(500),
                                    "percent" to 0,
                                    "stage" to "Error",
                                    "indeterminate" to false,
                                    "speed" to "",
                                    "eta" to ""
                                )
                            )
                        }
                    }
                } finally {
                    subWatcherRunning.set(false)
                    try {
                        workDir.deleteRecursively()
                    } catch (_: Throwable) {
                    }
                    pruneJobs()
                }
            }

            return JSONObject().put("ok", true).put("id", jid).put("folder", formatDisplayFolder(outDir.absolutePath)).toString()
        }
    }
}
