package com.leonidascan.app;

import android.content.Context;
import android.graphics.Bitmap;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 映射表：body_type → 游戏车名 / 车辆价值。
 * 数据来自 assets/mapping.csv（与 现实车-游戏车映射表.csv 同源）。
 */
public class CarDb {

    public static class Row {
        public String brand;
        public String body;
        public String display;
        public int value;
    }

    private final Map<String, List<Row>> byBody = new HashMap<>();
    private final List<Row> all = new ArrayList<>();

    public CarDb(Context ctx) throws IOException {
        try (BufferedReader br = new BufferedReader(new InputStreamReader(
                ctx.getAssets().open("mapping.csv"), StandardCharsets.UTF_8))) {

            String header = br.readLine();          // 跳过表头
            if (header != null && header.startsWith("\uFEFF")) header = header.substring(1);

            String line;
            while ((line = br.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] f = line.split(",", -1);
                if (f.length < 8) continue;

                Row r = new Row();
                r.brand = f[0].trim();
                r.body = f[1].trim();
                r.display = f[2].trim();
                try {
                    r.value = Integer.parseInt(f[7].trim());
                } catch (NumberFormatException e) {
                    continue;
                }
                all.add(r);
                byBody.computeIfAbsent(r.body, k -> new ArrayList<>()).add(r);
            }
        }
    }

    /**
     * 按车身形式取一条。优先真实品牌行，没有就用 * 兜底行。
     * seed 用同一块车牌的哈希，保证同一辆车每次扫出来一样。
     */
    public Row pick(String body, int seed) {
        List<Row> list = byBody.get(body);
        if (list == null || list.isEmpty()) {
            list = byBody.get("*");
        }
        if (list == null || list.isEmpty()) {
            return null;
        }
        // 去掉兜底行后的真实行
        List<Row> real = new ArrayList<>();
        for (Row r : list) {
            if (!"*".equals(r.brand)) real.add(r);
        }
        if (real.isEmpty()) real = list;

        int idx = Math.floorMod(seed, real.size());
        return real.get(idx);
    }

    /** 登记费：车值 1%，下限 $100，取整到 $50 */
    public static int fee(int value) {
        return Math.max(100, (int) (Math.round(value * 0.01 / 50.0) * 50));
    }

    /** 从位图主色猜车身颜色（只取框中部区域） */
    public static String colorName(Bitmap bmp, Detector.Box box) {
        if (bmp == null || box == null) return "未知";
        int w = bmp.getWidth(), h = bmp.getHeight();

        int l = (int) (box.l * w), r = (int) (box.r * w);
        int t = (int) (box.t * h), b = (int) (box.b * h);
        int cw = Math.max(1, r - l), ch = Math.max(1, b - t);

        long sr = 0, sg = 0, sb = 0;
        int n = 0;
        for (int i = 1; i <= 4; i++) {
            for (int j = 1; j <= 4; j++) {
                int x = l + cw * i / 5;
                int y = t + ch * j / 5;
                if (x < 0 || y < 0 || x >= w || y >= h) continue;
                int c = bmp.getPixel(x, y);
                sr += (c >> 16) & 0xFF;
                sg += (c >> 8) & 0xFF;
                sb += c & 0xFF;
                n++;
            }
        }
        if (n == 0) return "未知";
        return nearest((int) (sr / n), (int) (sg / n), (int) (sb / n));
    }

    private static final String[] NAMES = {
            "珍珠白", "厂矿银", "石墨灰", "曜石黑", "竞速红", "深海蓝", "竞速黄", "森林绿"
    };
    private static final int[][] PALETTE = {
            {238, 238, 236}, {176, 180, 185}, {116, 120, 124}, {28, 30, 34},
            {186, 32, 44}, {28, 70, 150}, {226, 190, 44}, {34, 128, 82}
    };

    private static String nearest(int r, int g, int b) {
        int best = 0;
        double bestD = Double.MAX_VALUE;
        for (int i = 0; i < PALETTE.length; i++) {
            int dr = r - PALETTE[i][0], dg = g - PALETTE[i][1], db = b - PALETTE[i][2];
            double d = dr * dr * 0.3 + dg * dg * 0.6 + db * db * 0.1;
            if (d < bestD) { bestD = d; best = i; }
        }
        return NAMES[best];
    }
}
