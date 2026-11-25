package com.leonidascan.app;

import android.graphics.Bitmap;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 车牌识别：ML Kit 中文 OCR + 车牌规则。
 * 注意：这里只做"读号牌"，不做任何车主信息查询（法律不允许）。
 */
public class PlateReader {

    private static final Pattern PLATE = Pattern.compile(
            "[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领]"
                    + "[A-Z][A-Z0-9]{5,6}");

    public interface Callback {
        void onResult(String plate, String raw);
    }

    private final TextRecognizer recognizer =
            TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());

    public void read(Bitmap bmp, Callback cb) {
        if (bmp == null) {
            cb.onResult(null, null);
            return;
        }
        InputImage img = InputImage.fromBitmap(bmp, 0);
        recognizer.process(img)
                .addOnSuccessListener(text -> cb.onResult(extract(text), text.getText()))
                .addOnFailureListener(e -> cb.onResult(null, null));
    }

    private static String extract(Text text) {
        List<String> candidates = new ArrayList<>();
        for (Text.TextBlock block : text.getTextBlocks()) {
            candidates.add(block.getText());
            for (Text.Line line : block.getLines()) {
                candidates.add(line.getText());
            }
        }
        for (String raw : candidates) {
            String n = normalize(raw);
            Matcher m = PLATE.matcher(n);
            if (m.find()) {
                return m.group();
            }
        }
        return null;
    }

    /** 去掉空格、点、横杠等干扰字符，转大写 */
    private static String normalize(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= 'a' && c <= 'z') c = (char) (c - 32);
            if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || isProvince(c)) {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private static boolean isProvince(char c) {
        return "京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领".indexOf(c) >= 0;
    }

    public void close() {
        try { recognizer.close(); } catch (Throwable ignored) { }
    }
}
