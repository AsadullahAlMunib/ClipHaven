package com.asadullahalmunib.cliphaven

import android.net.Uri
import java.util.Locale

internal object FormatUtils {
    val ALLOWED_DOMAINS = setOf(
        "youtube.com", "youtu.be", "youtube-nocookie.com", "facebook.com", "fb.watch", "fb.com", "fb.gg",
        "instagram.com", "instagr.am", "threads.net", "threads.com", "linkedin.com", "lnkd.in",
        "tiktok.com", "twitter.com", "x.com", "t.co", "reddit.com", "redd.it", "vimeo.com",
        "dailymotion.com", "dai.ly", "twitch.tv", "pinterest.com", "pin.it", "soundcloud.com", "snd.sc"
    )
    val VALID_FORMATS = setOf("mp4", "mkv", "webm", "mp3", "m4a", "wav")
    val VALID_QUALITIES = setOf("best", "2160", "1440", "1080", "720", "480", "360")

    fun isAllowedHost(host: String?): Boolean {
        val h = (host ?: "").lowercase().trimEnd('.')
        if (h.isEmpty()) return false
        return ALLOWED_DOMAINS.any { d -> h == d || h.endsWith(".$d") }
    }

    fun extractUrl(raw: String?): String {
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

    fun isValidUrl(raw: String?): Boolean {
        val url = extractUrl(raw)
        return try {
            val u = Uri.parse(url)
            u.scheme?.lowercase() == "https" && isAllowedHost(u.host)
        } catch (_: Throwable) {
            false
        }
    }


    fun parseTimestamp(ts: String): Int? {
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

    fun formatSeconds(sec: Int): String {
        val clean = sec.coerceAtLeast(0)
        val h = clean / 3600
        val m = (clean % 3600) / 60
        val s = clean % 60
        return if (h > 0) String.format(Locale.US, "%02d:%02d:%02d", h, m, s) else String.format(Locale.US, "%02d:%02d", m, s)
    }


    private val PUBLIC_RELEASE_TAG_REGEX = Regex("""^[vV](\d+\.\d+\.\d+)(?:[-+].*)?$""")

    fun extractPublicReleaseVersion(tagName: String?): String? {
        val m = PUBLIC_RELEASE_TAG_REGEX.matchEntire((tagName ?: "").trim()) ?: return null
        return m.groupValues[1]
    }

    fun parseSemver(ver: String?): List<Int> {
        if (ver.isNullOrBlank()) return listOf(0, 0, 0)
        val nums = Regex("""\d+""").findAll(ver).mapNotNull { it.value.toIntOrNull() }.take(4).toList()
        return if (nums.isEmpty()) listOf(0, 0, 0) else nums
    }

    fun isNewerVersion(latest: String?, current: String): Boolean {
        val a = parseSemver(latest)
        val b = parseSemver(current)
        val maxLen = maxOf(a.size, b.size)
        for (i in 0 until maxLen) {
            val av = a.getOrElse(i) { 0 }
            val bv = b.getOrElse(i) { 0 }
            if (av != bv) return av > bv
        }
        return false
    }


    fun compressPlaylistIndices(raw: String): String {
        val cleaned = raw.replace(Regex("""\s+"""), "")
        if (cleaned.isEmpty() || cleaned.contains("-") || !cleaned.contains(",")) return cleaned
        val nums = cleaned.split(",").mapNotNull { it.toIntOrNull() }.filter { it > 0 }.distinct().sorted()
        if (nums.isEmpty()) return cleaned
        val ranges = mutableListOf<String>()
        var start = nums[0]
        var prev = nums[0]
        for (i in 1 until nums.size) {
            val cur = nums[i]
            if (cur == prev + 1) {
                prev = cur
            } else {
                ranges.add(if (start == prev) "$start" else "$start-$prev")
                start = cur
                prev = cur
            }
        }
        ranges.add(if (start == prev) "$start" else "$start-$prev")
        return ranges.joinToString(",")
    }

}
