package com.asadullahalmunib.cliphaven

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

internal object PlaylistHelper {
    fun findInnerContinuationToken(node: Any?): String {
        when (node) {
            is JSONObject -> {
                for (key in listOf("token", "continuation")) {
                    val direct = node.optString(key, "").trim()
                    if (direct.length > 12) return direct
                }
                val keys = node.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    val found = findInnerContinuationToken(node.opt(k))
                    if (found.isNotEmpty()) return found
                }
            }
            is JSONArray -> {
                for (i in 0 until node.length()) {
                    val found = findInnerContinuationToken(node.opt(i))
                    if (found.isNotEmpty()) return found
                }
            }
        }
        return ""
    }

    fun parseYouTubeVideoItem(item: JSONObject): Triple<String, String, String>? {
        val unwrapped = item.optJSONObject("richItemRenderer")?.optJSONObject("content") ?: item

        // 1. Legacy shape: playlistVideoRenderer
        val pvr = unwrapped.optJSONObject("playlistVideoRenderer")
        if (pvr != null) {
            val vid = pvr.optString("videoId", "").trim()
            if (vid.isEmpty()) return null
            val titleObj = pvr.optJSONObject("title")
            val title = titleObj?.optJSONArray("runs")?.optJSONObject(0)?.optString("text", "")
                ?.ifEmpty { titleObj.optString("simpleText", "") }
                ?: pvr.optString("title", "")
            var dur = pvr.optJSONObject("lengthText")?.optString("simpleText", "")?.trim() ?: ""
            if (dur.isEmpty()) {
                val lSec = pvr.optInt("lengthSeconds", 0)
                if (lSec > 0) dur = FormatUtils.formatSeconds(lSec)
            }
            return Triple(vid, title.ifEmpty { "Video" }, dur)
        }

        // 2. Current 2026 shape: lockupViewModel
        val lvm = unwrapped.optJSONObject("lockupViewModel")
        if (lvm != null) {
            val vid = lvm.optString("contentId", "").trim()
            if (vid.isEmpty()) return null
            val title = lvm.optJSONObject("metadata")
                ?.optJSONObject("lockupMetadataViewModel")
                ?.optJSONObject("title")
                ?.optString("content", "")
                ?.trim()
                ?: ""
            var dur = ""
            val overlays = lvm.optJSONObject("contentImage")
                ?.optJSONObject("thumbnailViewModel")
                ?.optJSONArray("overlays")
            if (overlays != null) {
                for (i in 0 until overlays.length()) {
                    val ov = overlays.optJSONObject(i) ?: continue
                    val badges = ov.optJSONObject("thumbnailBottomOverlayViewModel")?.optJSONArray("badges")
                    if (badges != null) {
                        for (j in 0 until badges.length()) {
                            val bText = badges.optJSONObject(j)
                                ?.optJSONObject("thumbnailBadgeViewModel")
                                ?.optString("text", "")
                                ?.trim()
                                ?: ""
                            if (bText.contains(":")) {
                                dur = bText
                                break
                            }
                        }
                    }
                    if (dur.isEmpty()) {
                        val tText = ov.optJSONObject("thumbnailOverlayTimeStatusRenderer")
                            ?.optJSONObject("text")
                            ?.optString("simpleText", "")
                            ?.trim()
                            ?: ""
                        if (tText.contains(":")) dur = tText
                    }
                    if (dur.isNotEmpty()) break
                }
            }
            return Triple(vid, title.ifEmpty { "Video" }, dur)
        }
        return null
    }

    fun collectPlaylistVideosAndTokens(
        node: Any?,
        videosOut: MutableList<Triple<String, String, String>>,
        tokensOut: MutableList<String>
    ) {
        when (node) {
            is JSONObject -> {
                if (node.has("playlistVideoRenderer") || node.has("lockupViewModel")) {
                    val parsed = parseYouTubeVideoItem(node)
                    if (parsed != null) {
                        videosOut.add(parsed)
                        return
                    }
                }
                if (node.has("continuationItemViewModel") || node.has("continuationItemRenderer") || node.has("nextContinuationData")) {
                    val sub = node.opt("continuationItemViewModel")
                        ?: node.opt("continuationItemRenderer")
                        ?: node.opt("nextContinuationData")
                    val tok = findInnerContinuationToken(sub)
                    if (tok.isNotEmpty() && tok !in tokensOut) {
                        tokensOut.add(tok)
                    }
                    return
                }
                // Traverse itemSectionRenderer / playlistVideoListRenderer / appendContinuationItemsAction / contents first
                // so inner video-list tokens are always collected BEFORE outer sectionListRenderer tokens!
                val priorityKeys = listOf(
                    "contents",
                    "twoColumnBrowseResultsRenderer",
                    "singleColumnBrowseResultsRenderer",
                    "tabs",
                    "tabRenderer",
                    "content",
                    "sectionListRenderer",
                    "itemSectionRenderer",
                    "playlistVideoListRenderer",
                    "onResponseReceivedActions",
                    "onResponseReceivedEndpoints",
                    "appendContinuationItemsAction",
                    "reloadContinuationItemsCommand",
                    "continuationItems",
                    "continuationContents",
                    "playlistVideoListContinuation",
                    "continuations"
                )
                val visited = mutableSetOf<String>()
                for (pk in priorityKeys) {
                    if (node.has(pk)) {
                        visited.add(pk)
                        collectPlaylistVideosAndTokens(node.opt(pk), videosOut, tokensOut)
                    }
                }
                val keys = node.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    if (k !in visited) {
                        collectPlaylistVideosAndTokens(node.opt(k), videosOut, tokensOut)
                    }
                }
            }
            is JSONArray -> {
                for (i in 0 until node.length()) {
                    collectPlaylistVideosAndTokens(node.opt(i), videosOut, tokensOut)
                }
            }
        }
    }

    fun postYouTubeInnerTubeBrowse(
        payload: JSONObject,
        apiKey: String = "",
        visitorData: String = "",
        clientVersion: String = "2.20261101.01.00",
        cookieHeader: String = ""
    ): JSONObject? {
        val keyParam = if (apiKey.isNotEmpty()) "&key=$apiKey" else ""
        val endpoint = URL("https://www.youtube.com/youtubei/v1/browse?prettyPrint=false$keyParam")
        val conn = (endpoint.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 8000
            readTimeout = 10000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Origin", "https://www.youtube.com")
            setRequestProperty("Referer", "https://www.youtube.com/")
            setRequestProperty("X-YouTube-Client-Name", "1")
            setRequestProperty("X-YouTube-Client-Version", clientVersion)
            if (visitorData.isNotEmpty()) {
                setRequestProperty("X-Goog-Visitor-Id", visitorData)
            }
            if (cookieHeader.isNotEmpty()) {
                setRequestProperty("Cookie", cookieHeader)
            }
            setRequestProperty(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }
        return try {
            val bytes = payload.toString().toByteArray(Charsets.UTF_8)
            conn.outputStream.use { it.write(bytes) }
            if (conn.responseCode != 200) return null
            val text = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            JSONObject(text)
        } catch (_: Throwable) {
            null
        } finally {
            conn.disconnect()
        }
    }


    fun fetchYouTubePlaylistPage1Fast(listId: String): JSONObject? {
        if (listId.isEmpty() || listId.startsWith("RD")) return null
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL("https://www.youtube.com/playlist?list=${URLEncoder.encode(listId, "UTF-8")}&hl=en&gl=US").openConnection() as HttpURLConnection).apply {
                connectTimeout = 4500
                readTimeout = 4500
                setRequestProperty("Cookie", "CONSENT=YES+cb.20210328-17-p0.en+FX+410; PREF=hl=en&gl=US")
                setRequestProperty("Accept-Language", "en-US,en;q=0.9")
                setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                )
            }
            if (conn.responseCode != 200) return null
            val html = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            var rootObj: JSONObject? = null
            for (marker in listOf("var ytInitialData = ", "window[\"ytInitialData\"] = ")) {
                val mIdx = html.indexOf(marker)
                if (mIdx != -1) {
                    val jsonStart = mIdx + marker.length
                    val endIdx = html.indexOf(";</script>", jsonStart)
                    if (endIdx != -1) {
                        rootObj = JSONObject(html.substring(jsonStart, endIdx).trim())
                        break
                    }
                }
            }
            if (rootObj == null) return null

            val videos = mutableListOf<Triple<String, String, String>>()
            val tokens = mutableListOf<String>()
            collectPlaylistVideosAndTokens(rootObj, videos, tokens)
            if (videos.isEmpty()) return null

            val title = rootObj.optJSONObject("metadata")
                ?.optJSONObject("playlistMetadataRenderer")
                ?.optString("title", "")
                ?.trim()
                ?.ifEmpty {
                    rootObj.optJSONObject("microformat")
                        ?.optJSONObject("microformatDataRenderer")
                        ?.optString("title", "")
                        ?.trim()
                        ?: ""
                }
                ?.ifEmpty {
                    rootObj.optJSONObject("header")
                        ?.optJSONObject("playlistHeaderRenderer")
                        ?.optJSONObject("title")
                        ?.optString("simpleText", "")
                        ?.trim()
                        ?: ""
                }
                ?.ifEmpty { "YouTube Playlist" }
                ?: "YouTube Playlist"

            val uploader = rootObj.optJSONObject("header")
                ?.optJSONObject("playlistHeaderRenderer")
                ?.optJSONObject("ownerText")
                ?.optJSONArray("runs")
                ?.optJSONObject(0)
                ?.optString("text", "")
                ?.trim()
                ?.ifEmpty { "YouTube" }
                ?: "YouTube"

            val numStr = rootObj.optJSONObject("header")
                ?.optJSONObject("playlistHeaderRenderer")
                ?.optJSONObject("numVideosText")
                ?.optJSONArray("runs")
                ?.optJSONObject(0)
                ?.optString("text", "")
                ?.replace(",", "")
                ?.trim()
                ?: ""
            val parsedCount = numStr.toIntOrNull() ?: 0
            val reportedCount = maxOf(parsedCount, videos.size)

            val entriesArr = JSONArray()
            videos.forEachIndexed { idx, (vid, vTitle, vDur) ->
                entriesArr.put(
                    JSONObject()
                        .put("index", idx + 1)
                        .put("id", vid)
                        .put("title", vTitle.ifEmpty { "Video ${idx + 1}" })
                        .put("duration_str", vDur)
                )
            }
            val firstVid = videos.first().first
            val thumb = if (firstVid.isNotEmpty()) "https://i.ytimg.com/vi/$firstVid/hqdefault.jpg" else ""
            JSONObject()
                .put("_type", "playlist")
                .put("title", title)
                .put("uploader", uploader)
                .put("thumbnail", thumb)
                .put("playlist_count", reportedCount)
                .put("entries", entriesArr)
                .put("webpage_url", "https://www.youtube.com/playlist?list=$listId")
        } catch (_: Throwable) {
            null
        } finally {
            try { conn?.disconnect() } catch (_: Throwable) {}
        }
    }
}
