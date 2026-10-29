package com.asadullah.cliphaven

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private val jobs = ConcurrentHashMap<String, JSONObject>()

    private val defaultDownloadDir: File by lazy {
        val pub = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        File(pub, "ClipHaven").apply { mkdirs() }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        thread {
            try {
                YoutubeDL.getInstance().init(applicationContext)
                FFmpeg.getInstance().init(applicationContext)
            } catch (_: Exception) {
            }
        }

        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            @Suppress("DEPRECATION")
            allowUniversalAccessFromFileURLs = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                handleIncomingShareIntent(intent)
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val u = request?.url ?: return false
                if (u.scheme == "http" || u.scheme == "https") {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, u))
                    } catch (_: Exception) {
                    }
                    return true
                }
                return false
            }
        }
        webView.webChromeClient = WebChromeClient()
        webView.addJavascriptInterface(ClipHavenBridge(), "ClipHavenAndroid")
        webView.loadUrl("file:///android_asset/index.html")
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        if (intent != null) {
            handleIncomingShareIntent(intent)
        }
    }

    private fun handleIncomingShareIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
            val escaped = JSONObject.quote(sharedText)
            webView.post {
                webView.evaluateJavascript(
                    "if(document.getElementById('url')){document.getElementById('url').value=$escaped;triggerPreview();}",
                    null
                )
            }
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
        return if (h > 0) String.format("%02d:%02d:%02d", h, m, s) else String.format("%02d:%02d", m, s)
    }

    private fun showFolderPickerDialog(currentFolder: String): String? {
        val latch = CountDownLatch(1)
        var selectedPath: String? = null
        val dlRoot = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        val presets = arrayOf(
            File(dlRoot, "ClipHaven").absolutePath,
            File(dlRoot, "ClipHaven/Videos").absolutePath,
            File(dlRoot, "ClipHaven/Audio").absolutePath,
            dlRoot.absolutePath,
            "Custom subfolder inside Downloads…"
        )
        runOnUiThread {
            try {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Select Save Folder")
                    .setItems(presets) { _, which ->
                        if (which < 4) {
                            selectedPath = presets[which]
                            latch.countDown()
                        } else {
                            val input = EditText(this@MainActivity).apply {
                                setText(currentFolder.ifEmpty { File(dlRoot, "ClipHaven").absolutePath })
                            }
                            AlertDialog.Builder(this@MainActivity)
                                .setTitle("Enter Save Folder Path")
                                .setView(input)
                                .setPositiveButton("OK") { _, _ ->
                                    selectedPath = input.text.toString().trim()
                                    latch.countDown()
                                }
                                .setNegativeButton("Cancel") { _, _ -> latch.countDown() }
                                .setOnCancelListener { latch.countDown() }
                                .show()
                        }
                    }
                    .setNegativeButton("Cancel") { _, _ -> latch.countDown() }
                    .setOnCancelListener { latch.countDown() }
                    .show()
            } catch (_: Exception) {
                latch.countDown()
            }
        }
        latch.await(120, TimeUnit.SECONDS)
        return selectedPath
    }

    inner class ClipHavenBridge {
        @JavascriptInterface
        fun requestAsync(reqId: String, path: String, method: String, bodyRaw: String) {
            thread {
                val resJson = request(path, method, bodyRaw)
                val qId = JSONObject.quote(reqId)
                webView.post {
                    webView.evaluateJavascript(
                        "window.__onAndroidApiResult && window.__onAndroidApiResult($qId, $resJson);",
                        null
                    )
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
                } catch (_: Exception) {
                    JSONObject()
                }

                when (cleanPath) {
                    "/api/config" -> {
                        val arr = JSONArray()
                        jobs.values.toList().takeLast(10).forEach { arr.put(it) }
                        JSONObject()
                            .put("ok", true)
                            .put("version", "3.0.0")
                            .put("author", "Md Asadullah Al Munib")
                            .put("repo_url", "https://github.com/AsadullahAlMunib/ClipHaven/")
                            .put("default_folder", defaultDownloadDir.absolutePath)
                            .put("ffmpeg", true)
                            .put("jobs", arr)
                            .toString()
                    }
                    "/api/ffmpeg" -> JSONObject().put("ok", true).put("available", true).toString()
                    "/api/status" -> {
                        val id = uri.getQueryParameter("id") ?: ""
                        val j = jobs[id]
                        if (j != null) {
                            JSONObject(j.toString()).put("ok", true).toString()
                        } else {
                            JSONObject().put("ok", false).put("error", "Download job not found.").toString()
                        }
                    }
                    "/api/info" -> {
                        val url = body.optString("url", "").trim()
                        val req = YoutubeDLRequest(url).apply {
                            addOption("--dump-single-json")
                            addOption("--flat-playlist")
                            addOption("--playlist-end", "50")
                            addOption("--no-warnings")
                        }
                        val res = YoutubeDL.getInstance().execute(req)
                        val rawOut = res.out.trim()
                        val jsonLine = rawOut.lineSequence().lastOrNull { it.trim().startsWith("{") } ?: rawOut
                        val data = JSONObject(jsonLine)
                        val entries = data.optJSONArray("entries")
                        val isPlaylist = data.optString("_type") == "playlist" || (entries != null && entries.length() > 0)
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
                        } else if (isPlaylist && entries != null) {
                            entries.length()
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
                        YoutubeDL.getInstance().destroyProcessById(id)
                        jobs[id]?.apply {
                            put("state", "Cancelled")
                            put("title", "Download cancelled")
                            put("detail", "Download cancelled and temporary files cleaned up.")
                            put("stage", "Cancelled")
                            put("indeterminate", false)
                        }
                        JSONObject().put("ok", true).toString()
                    }
                    "/api/open-folder" -> {
                        runOnUiThread {
                            try {
                                startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS))
                            } catch (_: Exception) {
                            }
                        }
                        JSONObject().put("ok", true).toString()
                    }
                    "/api/pick-folder" -> {
                        val current = body.optString("current", defaultDownloadDir.absolutePath)
                        val chosen = showFolderPickerDialog(current)
                        if (chosen.isNullOrBlank()) {
                            JSONObject().put("ok", true).put("cancelled", true).put("folder", "").toString()
                        } else {
                            val dir = File(chosen).apply { mkdirs() }
                            JSONObject().put("ok", true).put("cancelled", false).put("folder", dir.absolutePath).toString()
                        }
                    }
                    else -> JSONObject().put("ok", false).put("error", "Not found.").toString()
                }
            } catch (e: Exception) {
                JSONObject().put("ok", false).put("error", e.message ?: "Request failed").toString()
            }
        }

        private fun startDownloadJob(body: JSONObject): String {
            val url = body.optString("url", "").trim()
            val folderRaw = body.optString("folder", "").trim()
            val fmt = body.optString("format", "mp4").lowercase().trim()
            val quality = body.optString("quality", "best").trim()
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

            val clipDuration = when {
                eSec != null && sSec != null -> (eSec - sSec).coerceAtLeast(1)
                durationHint > (sSec ?: 0) -> (durationHint - (sSec ?: 0)).coerceAtLeast(1)
                else -> 0
            }

            val outDir = (if (folderRaw.isNotEmpty()) File(folderRaw) else defaultDownloadDir).apply { mkdirs() }
            val jid = UUID.randomUUID().toString().replace("-", "")
            val isClipJob = startTime.isNotEmpty() || endTime.isNotEmpty()
            val job = JSONObject()
                .put("id", jid)
                .put("state", "Downloading")
                .put("title", if (isClipJob) "Preparing clip cutter…" else "Starting download")
                .put("video_title", if (titleHint.isNotEmpty()) titleHint else "ClipHaven download")
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
                .put("folder", outDir.absolutePath)
                .put("file_path", outDir.absolutePath)
            jobs[jid] = job

            thread {
                try {
                    val req = YoutubeDLRequest(url).apply {
                        addOption(if (allowPlaylist) "--yes-playlist" else "--no-playlist")
                        addOption("--newline")
                        addOption("--no-mtime")
                        if (fmt in setOf("mp3", "m4a", "wav")) {
                            addOption("-x")
                            addOption("--audio-format", fmt)
                            addOption("--audio-quality", "0")
                        } else {
                            val fExpr = if (quality == "best") "bv*+ba/b" else "bv*[height<=$quality]+ba/b[height<=$quality]/b"
                            addOption("--format", fExpr)
                            addOption("--merge-output-format", fmt)
                        }
                        var clipSuffix = ""
                        if (isClipJob) {
                            val endPart = eSec?.toString() ?: "inf"
                            addOption("--download-sections", "*${sSec ?: 0}-$endPart")
                            addOption("--force-keyframes-at-cuts")
                            clipSuffix = " [clip ${(startTime.ifEmpty { "0" }).replace(":", "-")}_to_${(endTime.ifEmpty { "end" }).replace(":", "-")}]"
                        }
                        if (subtitles) {
                            addOption("--write-subs")
                            addOption("--write-auto-subs")
                            addOption("--sub-langs", "orig,bn.*,en.*")
                            if (fmt in setOf("mp4", "mkv", "webm")) addOption("--embed-subs")
                        }
                        if (embedThumb && fmt in setOf("mp4", "mkv", "mp3", "m4a")) {
                            addOption("--embed-thumbnail")
                        }
                        addOption("-o", File(outDir, "%(title).160B [%(id)s]$clipSuffix.%(ext)s").absolutePath)
                    }

                    YoutubeDL.getInstance().execute(req, jid) { progress, etaInSeconds, line ->
                        val cleanLine = line.trim()
                        val plMatch = Regex("""\[download\] Downloading (?:item|video)\s+(\d+)\s+of\s+(\d+)""", RegexOption.IGNORE_CASE).find(cleanLine)
                        if (plMatch != null) {
                            val idx = plMatch.groupValues[1].toInt()
                            val tot = plMatch.groupValues[2].toInt()
                            job.put("playlist_index", idx)
                            job.put("playlist_total", tot)
                            job.put("playlist_done", (idx - 1).coerceAtLeast(0))
                            job.put("playlist_left", (tot - idx).coerceAtLeast(0))
                        }

                        val speedMatch = Regex("""at\s+([\d.]+\s*\w+/s)""").find(cleanLine)
                        if (speedMatch != null) {
                            job.put("speed", speedMatch.groupValues[1].trim())
                        }

                        val elapsedMatch = Regex("""\((\d{2}):(\d{2}):(\d{2})\)""").find(cleanLine)
                        if (progress > 0f) {
                            val pct = progress.coerceIn(0f, 100f)
                            job.put("percent", pct)
                            job.put("indeterminate", false)
                            job.put("eta", if (etaInSeconds > 0) formatSeconds(etaInSeconds.toInt()) else "")
                            job.put("title", if (isClipJob) "Cutting & downloading clip (${pct.toInt()}%)" else "Downloading (${pct.toInt()}%)")
                            job.put("stage", if (isClipJob) "Cutting clip" else "Downloading")
                        } else if (elapsedMatch != null && isClipJob) {
                            val curSec = elapsedMatch.groupValues[1].toInt() * 3600 + elapsedMatch.groupValues[2].toInt() * 60 + elapsedMatch.groupValues[3].toInt()
                            if (clipDuration > 0 && curSec > 0) {
                                val pct = ((curSec.toFloat() / clipDuration.toFloat()) * 100f).coerceIn(1f, 99f)
                                job.put("percent", pct)
                                job.put("indeterminate", false)
                                job.put("title", "Cutting & downloading clip (${pct.toInt()}%)")
                                job.put("stage", "Cutting clip")
                            }
                        }

                        when {
                            cleanLine.contains("Merging formats") || cleanLine.contains("[Merger]") -> {
                                job.put("title", "Merging video & audio (almost done)…")
                                job.put("stage", "Merging")
                                job.put("indeterminate", true)
                            }
                            cleanLine.contains("[ExtractAudio]") -> {
                                job.put("title", "Converting audio format…")
                                job.put("stage", "Converting audio")
                                job.put("indeterminate", true)
                            }
                            cleanLine.contains("Writing video subtitles") || cleanLine.contains("[EmbedSubtitle]") -> {
                                job.put("title", "Processing & embedding subtitles (CC)…")
                                job.put("stage", "Subtitles (CC)")
                                job.put("indeterminate", true)
                            }
                            cleanLine.contains("Downloading video thumbnail") || cleanLine.contains("[EmbedThumbnail]") -> {
                                job.put("title", "Embedding cover art / thumbnail…")
                                job.put("stage", "Embedding cover")
                                job.put("indeterminate", true)
                            }
                        }

                        if (cleanLine.isNotEmpty()) job.put("detail", cleanLine.take(500))
                    }

                    MediaScannerConnection.scanFile(applicationContext, arrayOf(outDir.absolutePath), null, null)
                    val plTot = job.optInt("playlist_total", 0)
                    if (plTot > 1) {
                        job.put("playlist_index", plTot)
                        job.put("playlist_done", plTot)
                        job.put("playlist_left", 0)
                    }
                    job.put("state", "Complete")
                    job.put("title", "Download complete!")
                    job.put("detail", "Saved to ${outDir.absolutePath}")
                    job.put("percent", 100)
                    job.put("indeterminate", false)
                    job.put("speed", "")
                    job.put("eta", "")
                    job.put("stage", "Complete")
                } catch (e: Exception) {
                    if (job.optString("state") != "Cancelled") {
                        job.put("state", "Error")
                        job.put("title", "Download failed")
                        job.put("detail", (e.message ?: "Download failed").take(500))
                        job.put("stage", "Error")
                        job.put("indeterminate", false)
                    }
                }
            }

            return JSONObject().put("ok", true).put("id", jid).put("folder", outDir.absolutePath).toString()
        }
    }
}
