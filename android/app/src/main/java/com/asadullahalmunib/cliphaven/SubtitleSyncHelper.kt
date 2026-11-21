package com.asadullahalmunib.cliphaven

import java.io.File
import java.util.Locale
import kotlin.math.roundToLong

internal object SubtitleSyncHelper {
    const val SUB_SHIFT_MARKER = "\u2060"
    val SUB_TS_LINE_REGEX = Regex("""((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})(.*)""")
    val SUB_INLINE_TS_REGEX = Regex("""<((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})>""")
    val SUB_OR_THUMB_EXTS = setOf(
        "vtt", "srt", "ass", "ssa", "ttml", "srv1", "srv2", "srv3", "json3",
        "webp", "jpg", "jpeg", "png", "part", "ytdl", "temp", "tmp"
    )
    val SUB_TEXT_EXTS = setOf("vtt", "srt")

    fun parseSubTimestampMs(ts: String): Long {
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

    fun formatSubTimestampMs(ms: Long, sep: Char): String {
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

    fun trimAndShiftSubtitleText(content: String, startSec: Int, endSec: Int?, isVtt: Boolean): String {
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

    fun hasActiveVideoFileInWorkDir(workDir: File): Boolean {
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

    fun syncClipSubtitlesInDir(workDir: File, startSec: Int, endSec: Int?, expectSrt: Boolean) {
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

}
