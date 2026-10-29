# Keep WebView JavascriptInterface bridge methods
-keepattributes JavascriptInterface
-keepattributes *Annotation*
-keepattributes Signature, InnerClasses, EnclosingMethod

-keepclassmembers class com.asadullah.cliphaven.MainActivity$ClipHavenBridge {
    @android.webkit.JavascriptInterface <methods>;
    public *;
}

# Keep youtubedl-android and embedded FFmpeg / Jackson classes
-keep class com.yausername.youtubedl_android.** { *; }
-keep class com.yausername.ffmpeg.** { *; }
-keep class com.yausername.common.** { *; }
-keep class com.fasterxml.jackson.** { *; }
-dontwarn com.fasterxml.jackson.**
-dontwarn org.apache.commons.io.**
