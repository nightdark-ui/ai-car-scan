package com.leonidascan.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.util.Log;

import org.tensorflow.lite.DataType;
import org.tensorflow.lite.Interpreter;
import org.tensorflow.lite.Tensor;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * EfficientDet-Lite0 (COCO) 封装。
 *
 * 两个坑：
 * 1) 模型带自定义算子 TFLite_Detection_PostProcess —— 标准 TFLite 的 BuiltinOpResolver
 *    里注册了它，可以用。
 * 2) 该算子的 4 个输出在 flatbuffer 里声明为「空形状」，allocateTensors 之后才变成
 *    [1,N,4] / [1,N] / [1,N] / [1]。如果按空形状去 new float[0] 会直接越界。
 *    这里做形状兜底 + 尺寸自适应重试。
 *
 * 只保留车相关类别：2=car 3=motorcycle 5=bus 7=truck
 */
public class Detector {

    private static final String TAG = "Detector";
    private static final String MODEL = "efficientdet_lite0.tflite";
    private static final float SCORE_THRESHOLD = 0.30f;
    private static final float MIN_AREA = 0.003f;

    private static final int[] DET_CANDIDATES = {25, 100, 10, 50};

    public static class Box {
        public float l, t, r, b;
        public int cls;
        public float score;

        public String label() {
            switch (cls) {
                case 2: return "car";
                case 3: return "motorcycle";
                case 5: return "bus";
                case 7: return "truck";
                default: return "car";
            }
        }

        public float area() { return Math.max(0, r - l) * Math.max(0, b - t); }
        public float cx() { return (l + r) * 0.5f; }
        public float cy() { return (t + b) * 0.5f; }
    }

    private final ByteBuffer modelBuffer;
    private Interpreter interp;

    private int inH = 320, inW = 320;
    private boolean isFloat;
    private boolean ready;

    private int idxBoxes = -1, idxA = -1, idxB = -1;
    private int[][] outShapes;
    private int detIdx = 0;
    private String shapeInfo = "";

    private boolean aIsClasses;
    private boolean classScoreKnown;

    private volatile String lastError = "";
    private volatile int lastCount = 0;
    private volatile float lastTopScore = 0f;

    public Detector(Context ctx) throws IOException {
        modelBuffer = readAsset(ctx, MODEL);
        create();
    }

    private void create() {
        Interpreter.Options opts = new Interpreter.Options();
        opts.setNumThreads(4);
        interp = new Interpreter(modelBuffer, opts);

        int[] inShape = interp.getInputTensor(0).shape();
        if (inShape.length >= 3) {
            inH = inShape[1];
            inW = inShape[2];
        }
        isFloat = interp.getInputTensor(0).dataType() == DataType.FLOAT32;

        try {
            interp.allocateTensors();
        } catch (Throwable t) {
            Log.w(TAG, "allocateTensors: " + t.getMessage());
        }

        resolveOutputs();
        ready = idxBoxes >= 0 && idxA >= 0 && idxB >= 0;
        Log.i(TAG, "input " + inW + "x" + inH + " float=" + isFloat
                + " ready=" + ready + " shapes=" + shapeInfo);
    }

    private void resolveOutputs() {
        int n = interp.getOutputTensorCount();
        outShapes = new int[n][];
        idxBoxes = -1;
        idxA = -1;
        idxB = -1;

        int fallbackN = DET_CANDIDATES[Math.min(detIdx, DET_CANDIDATES.length - 1)];
        StringBuilder sb = new StringBuilder();

        for (int i = 0; i < n; i++) {
            Tensor t = interp.getOutputTensor(i);
            int[] sh = t.shape();
            String nm = String.valueOf(t.name());

            if (sh == null || sh.length == 0) {
                if (nm.endsWith(":0")) sh = new int[]{1};
                else if (nm.endsWith(":1")) sh = new int[]{1, fallbackN, 4};
                else if (nm.endsWith(":2") || nm.endsWith(":3")) sh = new int[]{1, fallbackN};
                else sh = new int[]{1};
            }
            outShapes[i] = sh;
            sb.append(nm).append(Arrays.toString(sh)).append(' ');
        }
        shapeInfo = sb.toString().trim();

        for (int i = 0; i < n; i++) {
            int[] sh = outShapes[i];
            if (sh.length == 3 && sh[2] == 4) idxBoxes = i;
            else if (sh.length == 2) {
                if (idxA < 0) idxA = i;
                else if (idxB < 0) idxB = i;
            }
        }
    }

    public boolean isReady() { return ready; }
    public String lastError() { return lastError; }
    public int lastCount() { return lastCount; }
    public float lastTopScore() { return lastTopScore; }
    public String shapeInfo() { return shapeInfo; }

    private Object[] allocOutputsUnused() { return null; }

    public List<Box> detect(Bitmap src) {
        List<Box> out = new ArrayList<>();
        if (!ready || src == null || interp == null) return out;

        try {
            ByteBuffer in = buildInput(src);
            // outputs 传 null：不往 Object[] 里拷结果，直接从张量缓冲读。
            // 这个模型的输出是动态形状，数组形式的类型推断会失败。
            interp.run(in, null);
            parse(out);
            lastError = "";
        } catch (Throwable t) {
            lastError = t.getClass().getSimpleName() + ": " + t.getMessage();
            Log.e(TAG, "推理失败: " + lastError + " shapes=" + shapeInfo);
            lastCount = 0;
            lastTopScore = 0f;
        }
        return out;
    }

    private float[] readFloats(int idx, int count) {
        ByteBuffer bb = interp.getOutputTensor(idx).asReadOnlyBuffer();
        bb.order(ByteOrder.nativeOrder());
        FloatBuffer fb = bb.asFloatBuffer();
        int n = Math.min(count, fb.remaining());
        float[] arr = new float[count];
        if (n > 0) fb.get(arr, 0, n);
        return arr;
    }

    private void parse(List<Box> out) {
        int[] bs = interp.getOutputTensor(idxBoxes).shape();
        int N = (bs.length == 3) ? bs[1] : 0;
        if (N <= 0) return;

        float[] boxes = readFloats(idxBoxes, N * 4);
        float[] ra = readFloats(idxA, N);
        float[] rb = readFloats(idxB, N);

        if (!classScoreKnown) {
            aIsClasses = maxOf(ra) > maxOf(rb);
            classScoreKnown = true;
            Log.i(TAG, "aIsClasses=" + aIsClasses);
        }
        float[] classes = aIsClasses ? ra : rb;
        float[] scores = aIsClasses ? rb : ra;

        float top = 0f;
        for (int i = 0; i < N; i++) {
            float s = scores[i];
            if (s > top) top = s;
            if (s < SCORE_THRESHOLD) continue;

            int cls = Math.round(classes[i]);
            if (cls != 2 && cls != 3 && cls != 5 && cls != 7) continue;

            Box bx = new Box();
            bx.t = clamp01(boxes[i * 4]);
            bx.l = clamp01(boxes[i * 4 + 1]);
            bx.b = clamp01(boxes[i * 4 + 2]);
            bx.r = clamp01(boxes[i * 4 + 3]);
            bx.cls = cls;
            bx.score = s;
            if (bx.area() >= MIN_AREA) out.add(bx);
        }
        lastTopScore = top;
        lastCount = out.size();
    }

    private static float maxOf(float[] a) {
        float m = 0;
        for (float v : a) if (v > m) m = v;
        return m;
    }

    private ByteBuffer buildInput(Bitmap src) {
        Bitmap scaled = Bitmap.createScaledBitmap(src, inW, inH, true);
        int pxCount = inW * inH;
        int[] px = new int[pxCount];
        scaled.getPixels(px, 0, inW, 0, 0, inW, inH);

        ByteBuffer in = ByteBuffer.allocateDirect(pxCount * 3 * (isFloat ? 4 : 1));
        in.order(ByteOrder.nativeOrder());
        for (int i = 0; i < pxCount; i++) {
            int c = px[i];
            int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
            if (isFloat) {
                in.putFloat(r / 255f);
                in.putFloat(g / 255f);
                in.putFloat(b / 255f);
            } else {
                in.put((byte) r);
                in.put((byte) g);
                in.put((byte) b);
            }
        }
        in.rewind();
        if (scaled != src) scaled.recycle();
        return in;
    }

    private static float maxOf(float[][] a) {
        float m = 0;
        for (float[] r : a) for (float v : r) if (v > m) m = v;
        return m;
    }

    private static float clamp01(float v) {
        return v < 0 ? 0 : (v > 1 ? 1 : v);
    }

    public void close() {
        try { if (interp != null) interp.close(); } catch (Throwable ignored) { }
        interp = null;
        ready = false;
    }

    /**
     * TFLite 的 Interpreter 只接受「直接缓冲区」，heap 上的 ByteBuffer.wrap(byte[])
     * 会抛 IllegalArgumentException。这里手工拷贝到 allocateDirect。
     */
    private static ByteBuffer readAsset(Context ctx, String name) throws IOException {
        byte[] bytes;
        try (InputStream is = ctx.getAssets().open(name);
             ByteArrayOutputStream bos = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            bytes = bos.toByteArray();
        }
        ByteBuffer bb = ByteBuffer.allocateDirect(bytes.length);
        bb.order(ByteOrder.nativeOrder());
        bb.put(bytes);
        bb.rewind();
        return bb;
    }
}
