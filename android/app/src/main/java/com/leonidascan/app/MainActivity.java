package com.leonidascan.app;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Matrix;
import android.media.AudioAttributes;
import android.media.SoundPool;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.util.Size;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;

import com.google.common.util.concurrent.ListenableFuture;

import java.io.InputStream;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 原生相机 + TFLite 检测 + ML Kit 车牌，结果通过 JS Bridge 推给 WebView HUD。
 * 页面用 index.html?native=1 进入原生模式（透明背景、不自己开相机）。
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "LeonidaScan";
    private static final int REQ_CAMERA = 1001;
    private static final long ANALYZE_INTERVAL_MS = 150;

    private WebView web;
    private PreviewView preview;
    private ExecutorService io;

    private Detector detector;
    private PlateReader plateReader;
    private CarDb db;
    private String initError = "";
    private SoundPool soundPool;
    private int sndLock, sndScan, sndDone, sndCancel;
    private int scanStream = 0;

    private final Object frameLock = new Object();
    private Bitmap lastFrame;
    private final AtomicBoolean capturing = new AtomicBoolean(false);
    private volatile boolean cameraReady = false;
    private long lastPushAt = 0;
    private long lastAnalyzeAt = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        FrameLayout root = new FrameLayout(this);

        preview = new PreviewView(this);
        preview.setImplementationMode(PreviewView.ImplementationMode.COMPATIBLE);
        preview.setScaleType(PreviewView.ScaleType.FILL_CENTER);
        root.addView(preview, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        web = new WebView(this);
        web.setBackgroundColor(Color.TRANSPARENT);
        setupWebView();
        root.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        setContentView(root);
        applyFullscreen();
        setupSound();

        io = Executors.newSingleThreadExecutor();

        try {
            detector = new Detector(this);
            db = new CarDb(this);
            plateReader = new PlateReader();
            Log.i(TAG, "模型与映射表加载完成");
        } catch (Throwable t) {
            initError = t.getClass().getSimpleName() + ": " + t.getMessage();
            Log.e(TAG, "初始化失败", t);
        }

        web.loadUrl("file:///android_asset/index.html?native=1");

        // 启动后用内置图跑一次模型，把结果打到屏幕上（不依赖相机）
        new Handler(Looper.getMainLooper()).postDelayed(this::runSelfCheck, 2200);

        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera();
        } else {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA);
        }
    }

    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);

        web.setBackgroundColor(Color.TRANSPARENT);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                view.evaluateJavascript(
                        "window.__native&&window.__native.onReady&&window.__native.onReady()", null);
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> request.deny());
            }
        });

        web.addJavascriptInterface(new Bridge(), "Android");
    }

    // ---------------- 相机 ----------------

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> future = ProcessCameraProvider.getInstance(this);
        future.addListener(() -> {
            try {
                ProcessCameraProvider provider = future.get();

                Preview pv = new Preview.Builder().build();
                pv.setSurfaceProvider(preview.getSurfaceProvider());

                ImageAnalysis analysis = new ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                        .setTargetResolution(new Size(960, 540))
                        .build();
                analysis.setAnalyzer(io, this::analyze);

                provider.unbindAll();
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, pv, analysis);
                cameraReady = true;
                Log.i(TAG, "相机已启动");
            } catch (Throwable t) {
                Log.e(TAG, "相机启动失败", t);
                cameraReady = false;
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void analyze(@NonNull ImageProxy image) {
        long now = System.currentTimeMillis();

        if (now - lastAnalyzeAt < ANALYZE_INTERVAL_MS) {
            image.close();
            return;
        }
        lastAnalyzeAt = now;

        Bitmap bmp = null;
        try {
            bmp = image.toBitmap();
            int rot = image.getImageInfo().getRotationDegrees();
            if (rot != 0 && bmp != null) {
                Matrix m = new Matrix();
                m.postRotate(rot);
                Bitmap r2 = Bitmap.createBitmap(bmp, 0, 0, bmp.getWidth(), bmp.getHeight(), m, true);
                if (r2 != bmp) bmp.recycle();
                bmp = r2;
            }
        } catch (Throwable t) {
            Log.w(TAG, "取帧失败: " + t.getMessage());
        } finally {
            image.close();
        }
        if (bmp == null) return;

        synchronized (frameLock) {
            Bitmap old = lastFrame;
            lastFrame = bmp;
            if (old != null && old != bmp) old.recycle();
        }

        if (detector == null || !detector.isReady()) {
            if (now - lastPushAt >= 500) {
                lastPushAt = now;
                pushBoxes(new java.util.ArrayList<>());
            }
            return;
        }

        List<Detector.Box> boxes = detector.detect(bmp);
        if (now - lastPushAt >= ANALYZE_INTERVAL_MS) {
            lastPushAt = now;
            pushBoxes(boxes);
        }
    }

    /** YUV_420_888 → ARGB。image.toBitmap() 在这台机器上给了黑帧，手写转换更可靠 */
    private static Bitmap yuvToBitmap(ImageProxy image) {
        ImageProxy.PlaneProxy[] p = image.getPlanes();
        ByteBuffer yB = p[0].getBuffer();
        ByteBuffer uB = p[1].getBuffer();
        ByteBuffer vB = p[2].getBuffer();

        int yRowStride = p[0].getRowStride();
        int uvRowStride = p[1].getRowStride();
        int uvPixelStride = p[1].getPixelStride();

        byte[] y = new byte[yB.remaining()];
        yB.get(y);
        byte[] u = new byte[uB.remaining()];
        uB.get(u);
        byte[] v = new byte[vB.remaining()];
        vB.get(v);

        int w = image.getWidth(), h = image.getHeight();
        int[] argb = new int[w * h];

        for (int row = 0; row < h; row++) {
            int yBase = row * yRowStride;
            int uvBase = (row >> 1) * uvRowStride;
            for (int col = 0; col < w; col++) {
                int yi = yBase + col;
                if (yi >= y.length) continue;
                int Y = y[yi] & 0xFF;

                int ui = uvBase + (col >> 1) * uvPixelStride;
                int U = 128, V = 128;
                if (ui < u.length && ui < v.length) {
                    U = u[ui] & 0xFF;
                    V = v[ui] & 0xFF;
                }

                int c = Y - 16;
                int d = U - 128;
                int e = V - 128;
                int r = (298 * c + 409 * e + 128) >> 8;
                int g = (298 * c - 100 * d - 208 * e + 128) >> 8;
                int b = (298 * c + 516 * d + 128) >> 8;
                argb[row * w + col] = 0xFF000000
                        | (clamp255(r) << 16) | (clamp255(g) << 8) | clamp255(b);
            }
        }

        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        bmp.setPixels(argb, 0, w, 0, 0, w, h);
        return bmp;
    }

    private static int clamp255(int v) {
        return v < 0 ? 0 : (v > 255 ? 255 : v);
    }

    private void pushBoxes(List<Detector.Box> boxes) {
        StringBuilder sb = new StringBuilder("[");
        int n = 0;
        for (Detector.Box b : boxes) {
            if (n >= 3) break;
            if (n > 0) sb.append(',');
            sb.append('{')
              .append("\"l\":").append(round(b.l)).append(',')
              .append("\"t\":").append(round(b.t)).append(',')
              .append("\"r\":").append(round(b.r)).append(',')
              .append("\"b\":").append(round(b.b)).append(',')
              .append("\"label\":\"").append(b.label()).append("\",")
              .append("\"s\":").append(round(b.score))
              .append('}');
            n++;
        }
        sb.append(']');

        final String js = "window.__native&&window.__native.onDetect(" + sb + ")";
        runOnUiThread(() -> {
            if (web != null) web.evaluateJavascript(js, null);
        });
    }

    private String debugJson() {
        String err = detector == null ? ("detector=null " + initError) : detector.lastError();
        int cnt = detector == null ? 0 : detector.lastCount();
        float top = detector == null ? 0f : detector.lastTopScore();
        String sh = detector == null ? "" : detector.shapeInfo();
        return "{\"n\":" + cnt + ",\"top\":" + round(top)
                + ",\"cam\":" + (cameraReady ? 1 : 0)
                + ",\"lum\":" + frameLum()
                + ",\"v\":\"" + esc(BuildConfig.VERSION_NAME) + "\""
                + ",\"err\":\"" + esc(err == null ? "" : err) + "\""
                + ",\"sh\":\"" + esc(sh) + "\"}";
    }

    /** 取当前帧的平均亮度（0-255），用来判断相机是不是给了一张黑图 */
    private int frameLum() {
        Bitmap b;
        synchronized (frameLock) {
            b = lastFrame;
        }
        if (b == null) return -1;
        try {
            int w = b.getWidth(), h = b.getHeight();
            long sum = 0;
            int n = 0;
            for (int i = 1; i <= 8; i++) {
                for (int j = 1; j <= 8; j++) {
                    int x = w * i / 9, y = h * j / 9;
                    int c = b.getPixel(x, y);
                    int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, bl = c & 0xFF;
                    sum += (r * 299 + g * 587 + bl * 114) / 1000;
                    n++;
                }
            }
            return n == 0 ? -1 : (int) (sum / n);
        } catch (Throwable t) {
            return -1;
        }
    }

    private static String round(float v) {
        return String.valueOf(Math.round(v * 1000) / 1000.0);
    }

    // ---------------- 扫描 ----------------

    private void doCapture() {
        if (!capturing.compareAndSet(false, true)) return;

        Bitmap frame;
        synchronized (frameLock) {
            frame = lastFrame == null ? null : lastFrame.copy(Bitmap.Config.ARGB_8888, false);
        }

        if (frame == null) {
            capturing.set(false);
            sendResult("{\"ok\":false,\"reason\":\"no_frame\"}");
            return;
        }
        runCapture(frame, true);
    }

    private void runCapture(Bitmap frame, boolean recycleFrame) {
        if (detector == null || db == null || plateReader == null) {
            if (recycleFrame) frame.recycle();
            capturing.set(false);
            sendResult("{\"ok\":false,\"reason\":\"no_frame\"}");
            return;
        }

        io.execute(() -> {
            List<Detector.Box> boxes = detector.detect(frame);
            Detector.Box best = null;
            for (Detector.Box b : boxes) {
                if (best == null || b.area() > best.area()) best = b;
            }

            if (best == null) {
                if (recycleFrame) frame.recycle();
                capturing.set(false);
                String err = detector.lastError();
                sendResult("{\"ok\":false,\"reason\":\"no_target\",\"err\":\"" + esc(err) + "\"}");
                return;
            }

            final Detector.Box target = best;
            final String body = bodyOf(best.label());
            final String color = CarDb.colorName(frame, best);
            final Bitmap crop = crop(frame, best);

            plateReader.read(crop, (plate, raw) -> {
                int seed = plate != null ? plate.hashCode() : (int) (System.currentTimeMillis() / 1000);
                CarDb.Row row = db.pick(body, seed);
                String json = buildResult(row, body, color, plate, target.score);
                if (crop != null) crop.recycle();
                if (recycleFrame) frame.recycle();
                capturing.set(false);
                sendResult(json);
            });
        });
    }

    private static Bitmap crop(Bitmap src, Detector.Box box) {
        int w = src.getWidth(), h = src.getHeight();
        int l = (int) (box.l * w), t = (int) (box.t * h);
        int r = (int) (box.r * w), b = (int) (box.b * h);
        l = Math.max(0, l); t = Math.max(0, t);
        r = Math.min(w, r); b = Math.min(h, b);
        if (r - l < 16 || b - t < 16) return null;
        try {
            return Bitmap.createBitmap(src, l, t, r - l, b - t);
        } catch (Throwable e) {
            return null;
        }
    }

    private static String bodyOf(String label) {
        switch (label) {
            case "truck": return "皮卡";
            case "bus": return "MPV";
            case "motorcycle": return "摩托";
            default: return "轿车";
        }
    }

    private static String buildResult(CarDb.Row row, String body, String color,
                                      String plate, float score) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"ok\":true");
        sb.append(",\"kind\":\"VEHICLE · SCANNED\"");
        sb.append(",\"title\":\"").append(esc(row == null ? "未知" : row.display)).append("\"");
        sb.append(",\"sub\":\"SCAN ").append(1000 + (int) (System.currentTimeMillis() % 9000))
          .append(" · 置信度 ").append(Math.round(score * 100)).append("%\"");
        sb.append(",\"rows\":[");
        sb.append("[\"车身形式\",\"").append(esc(body)).append("\"],");
        sb.append("[\"车牌\",\"").append(esc(plate == null ? "未识别" : plate)).append("\"],");
        sb.append("[\"车身颜色\",\"").append(esc(color)).append("\"],");
        sb.append("[\"车辆价值\",\"").append(money(row == null ? 0 : row.value)).append("\",\"money\"],");
        sb.append("[\"登记费\",\"").append(money(row == null ? 0 : CarDb.fee(row.value))).append("\"],");
        sb.append("[\"防盗系统\",\"无法获取\"],");
        sb.append("[\"车主信息\",\"未知\"]");
        sb.append("]}");
        return sb.toString();
    }

    private static String money(int v) {
        return "$" + String.format("%,d", v);
    }

    private static String esc(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                default: sb.append(c);
            }
        }
        return sb.toString();
    }

    private void sendResult(String json) {
        final String js = "window.__native&&window.__native.onResult(" + json + ")";
        runOnUiThread(() -> {
            if (web != null) web.evaluateJavascript(js, null);
        });
    }

    // ---------------- 内置自检 ----------------

    /**
     * 用打包进来的图跑一次检测。结果直接显示在屏幕上，用来判断
     * 「模型本身有问题」还是「相机链路有问题」。
     */
    private void runSelfCheck() {
        if (detector == null) {
            pushSelfCheck(0, 0f, -1, "detector=null " + initError);
            return;
        }
        io.execute(() -> {
            Bitmap bmp = null;
            try (InputStream is = getAssets().open("selfcheck.jpg")) {
                bmp = BitmapFactory.decodeStream(is);
            } catch (Throwable t) {
                Log.e(TAG, "自检图读取失败", t);
            }
            if (bmp == null) {
                pushSelfCheck(0, 0f, -1, "no_selfcheck_asset");
                return;
            }
            int lum = avgLum(bmp);
            List<Detector.Box> boxes = detector.detect(bmp);
            int n = boxes.size();
            float top = detector.lastTopScore();
            String err = detector.lastError();
            bmp.recycle();
            pushSelfCheck(n, top, lum, err);
        });
    }

    private void pushSelfCheck(int n, float top, int lum, String err) {
        // 界面上不再显示诊断信息，只留 logcat
        Log.i(TAG, "selfcheck n=" + n + " top=" + top + " lum=" + lum
                + " err=" + (err == null ? "" : err));
    }

    private static int avgLum(Bitmap b) {
        try {
            int w = b.getWidth(), h = b.getHeight();
            long sum = 0;
            int n = 0;
            for (int i = 1; i <= 8; i++) {
                for (int j = 1; j <= 8; j++) {
                    int c = b.getPixel(w * i / 9, h * j / 9);
                    int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, bl = c & 0xFF;
                    sum += (r * 299 + g * 587 + bl * 114) / 1000;
                    n++;
                }
            }
            return n == 0 ? -1 : (int) (sum / n);
        } catch (Throwable t) {
            return -1;
        }
    }

    // ---------------- 音效 ----------------

    private void setupSound() {
        try {
            AudioAttributes attrs = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_GAME)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            soundPool = new SoundPool.Builder()
                    .setMaxStreams(4)
                    .setAudioAttributes(attrs)
                    .build();
            sndLock = soundPool.load(this, R.raw.sfx_lock, 1);
            sndScan = soundPool.load(this, R.raw.sfx_scan, 1);
            sndDone = soundPool.load(this, R.raw.sfx_done, 1);
            sndCancel = soundPool.load(this, R.raw.sfx_cancel, 1);
        } catch (Throwable t) {
            Log.e(TAG, "音效初始化失败", t);
        }
    }

    private void playSfx(String name) {
        if (soundPool == null || name == null) return;
        switch (name) {
            case "lock":
                soundPool.play(sndLock, 0.9f, 0.9f, 1, 0, 1f);
                break;
            case "scan":
                stopScanSound();
                scanStream = soundPool.play(sndScan, 0.75f, 0.75f, 1, -1, 1f);
                break;
            case "stop":
                stopScanSound();
                break;
            case "done":
                stopScanSound();
                soundPool.play(sndDone, 0.95f, 0.95f, 1, 0, 1f);
                break;
            case "cancel":
                stopScanSound();
                soundPool.play(sndCancel, 0.7f, 0.7f, 1, 0, 1f);
                break;
            default:
                break;
        }
    }

    private void stopScanSound() {
        if (scanStream != 0 && soundPool != null) {
            try { soundPool.stop(scanStream); } catch (Throwable ignored) { }
            scanStream = 0;
        }
    }

    // ---------------- JS 桥 ----------------

    public class Bridge {
        @JavascriptInterface
        public void capture() {
            doCapture();
        }

        @JavascriptInterface
        public void sfx(String name) {
            runOnUiThread(() -> playSfx(name));
        }

        @JavascriptInterface
        public void vibrate(int ms) {
            runOnUiThread(() -> {
                try {
                    android.os.Vibrator v =
                            (android.os.Vibrator) getSystemService(VIBRATOR_SERVICE);
                    if (v != null && v.hasVibrator()) v.vibrate(ms);
                } catch (Throwable ignored) { }
            });
        }

        @JavascriptInterface
        public boolean cameraReady() {
            return cameraReady;
        }
    }

    // ---------------- 生命周期 ----------------

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_CAMERA) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startCamera();
            } else {
                sendResult("{\"ok\":false,\"reason\":\"no_permission\"}");
            }
        }
    }

    @SuppressWarnings("deprecation")
    private void applyFullscreen() {
        Window w = getWindow();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController c = w.getInsetsController();
            if (c != null) {
                c.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                c.setSystemBarsBehavior(
                        WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            w.getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
        applyFullscreen();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) web.onPause();
    }

    @Override
    protected void onDestroy() {
        if (io != null) io.shutdownNow();
        if (detector != null) detector.close();
        if (plateReader != null) plateReader.close();
        synchronized (frameLock) {
            if (lastFrame != null) { lastFrame.recycle(); lastFrame = null; }
        }
        if (web != null) { web.destroy(); web = null; }
        super.onDestroy();
    }
}
