# Keep app classes and WebView JavascriptInterface bridge methods
-keepattributes JavascriptInterface
-keepattributes *Annotation*
-keepattributes Signature, InnerClasses, EnclosingMethod

-keep class com.asadullahalmunib.cliphaven.** { *; }
-keepclassmembers class com.asadullahalmunib.cliphaven.MainActivity$ClipHavenBridge {
    @android.webkit.JavascriptInterface <methods>;
    public *;
}

# Keep youtubedl-android, embedded FFmpeg, Apache Commons, and Jackson classes
-keep class com.yausername.youtubedl_android.** { *; }
-keep class com.yausername.ffmpeg.** { *; }
-keep class com.yausername.common.** { *; }
-keep class com.fasterxml.jackson.** { *; }
-keep class org.apache.commons.** { *; }
-dontwarn com.fasterxml.jackson.**
-dontwarn org.apache.commons.**
