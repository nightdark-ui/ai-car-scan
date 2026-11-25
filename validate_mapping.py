#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
映射表校验工具
用法:
    python validate_mapping.py [csv路径]

检查项:
    1. 表头完整性
    2. body_type 是否在允许集合内
    3. value_usd 是否为正整数
    4. display_cn 是否等于 "品牌 + 空格 + 车型"
    5. display_cn 是否与英文名冲突
    6. 是否存在完全重复行
    7. 兜底行(*) 是否覆盖所有车身形式，且每种只有一条
    8. 每个车身形式是否至少有一条真实品牌行
    9. 价格是否在合理区间

退出码: 0 无错误 / 1 有错误
"""

import csv
import sys
import os
from collections import Counter, defaultdict

# Windows 控制台默认是 GBK，强制 UTF-8 输出，避免中文和符号报错
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BODY_TYPES = ["轿车", "两厢", "SUV", "跑车", "皮卡", "MPV", "卡车", "摩托"]

COLUMNS = [
    "real_brand", "body_type", "display_cn",
    "game_brand_cn", "game_model_cn",
    "game_brand_en", "game_model_en",
    "value_usd", "note",
]

# 合理价格区间（游戏币）
PRICE_MIN = 1000
PRICE_MAX = 10_000_000

errors = []
warnings = []


def err(line, msg):
    errors.append((line, msg))


def warn(line, msg):
    warnings.append((line, msg))


def main(path):
    if not os.path.exists(path):
        print(f"找不到文件: {path}")
        return 1

    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print("文件是空的")
            return 1

        # 1. 表头
        if header != COLUMNS:
            missing = [c for c in COLUMNS if c not in header]
            extra = [c for c in header if c not in COLUMNS]
            if missing:
                err(1, f"缺少列: {', '.join(missing)}")
            if extra:
                err(1, f"多余列: {', '.join(extra)}")
            if not missing and not extra:
                err(1, f"列顺序不对，应为: {','.join(COLUMNS)}")

        rows = []
        for lineno, row in enumerate(reader, start=2):
            if not any((c or "").strip() for c in row):
                continue
            if len(row) != len(header):
                err(lineno, f"列数 {len(row)} ≠ 表头 {len(header)}")
                continue
            rows.append((lineno, dict(zip(header, row))))

    real_rows = [r for r in rows if r[1]["real_brand"].strip() != "*"]
    fallback_rows = [r for r in rows if r[1]["real_brand"].strip() == "*"]

    seen_display = {}
    seen_full = {}

    for lineno, d in rows:
        brand = d["real_brand"].strip()
        body = d["body_type"].strip()
        display = d["display_cn"].strip()
        gb_cn = d["game_brand_cn"].strip()
        gm_cn = d["game_model_cn"].strip()
        gb_en = d["game_brand_en"].strip()
        gm_en = d["game_model_en"].strip()
        value = d["value_usd"].strip()

        # 2. 车身形式
        if body not in BODY_TYPES:
            err(lineno, f"未知车身形式: {body!r}（应为 {'/'.join(BODY_TYPES)}）")

        # 3. 价格
        try:
            v = int(value)
            if v < PRICE_MIN or v > PRICE_MAX:
                warn(lineno, f"价格 ${v:,} 超出常见区间 ${PRICE_MIN:,}–${PRICE_MAX:,}")
        except ValueError:
            err(lineno, f"value_usd 不是整数: {value!r}")

        # 4. display_cn 拼接
        if not brand:
            err(lineno, "real_brand 为空")
        expected = f"{gb_cn} {gm_cn}".strip()
        if display != expected:
            err(lineno, f"display_cn {display!r} ≠ 品牌+车型 {expected!r}")

        # 5. display_cn 与英文冲突
        en_pair = (gb_en, gm_en)
        if display in seen_display and seen_display[display][0] != en_pair:
            err(lineno, f"display_cn {display!r} 与第 {seen_display[display][1]} 行的英文名不一致")
        else:
            seen_display.setdefault(display, (en_pair, lineno))

        # 6. 完全重复
        key = tuple(d[c].strip() for c in COLUMNS)
        if key in seen_full:
            err(lineno, f"与第 {seen_full[key]} 行完全重复")
        else:
            seen_full[key] = lineno

        # 9. 备注
        if not d["note"].strip():
            warn(lineno, "note 为空")

    # 7. 兜底覆盖
    fb_types = Counter(d["body_type"].strip() for _, d in fallback_rows)
    for bt in BODY_TYPES:
        if fb_types[bt] == 0:
            err(0, f"兜底行缺少车身形式: {bt}")
        elif fb_types[bt] > 1:
            err(0, f"兜底行 {bt} 重复 {fb_types[bt]} 次")

    # 8. 真实行覆盖（只对主力车型提示；MPV/卡车/摩托本来就只靠兜底）
    CORE_TYPES = {"轿车", "两厢", "SUV", "跑车"}
    real_types = Counter(d["body_type"].strip() for _, d in real_rows)
    for bt in BODY_TYPES:
        if bt in CORE_TYPES and real_types[bt] == 0:
            warn(0, f"没有真实车型映射到: {bt}（只能靠兜底）")

    # ---------------- 输出 ----------------
    print(f"文件: {path}")
    print(f"数据行: {len(rows)}  (真实 {len(real_rows)} / 兜底 {len(fallback_rows)})")
    print()

    if errors:
        print(f"✗ 错误 {len(errors)}")
        for line, msg in errors:
            print(f"   L{line}: {msg}" if line else f"   {msg}")
        print()
    if warnings:
        print(f"⚠ 警告 {len(warnings)}")
        for line, msg in warnings:
            print(f"   L{line}: {msg}" if line else f"   {msg}")
        print()

    if not errors and not warnings:
        print("✓ 全部通过")
        print()

    print("按车身形式统计:")
    for bt in BODY_TYPES:
        print(f"   {bt:<4}  真实 {real_types[bt]:>2}  兜底 {fb_types[bt]}")

    prices = [int(d["value_usd"]) for _, d in real_rows if d["value_usd"].strip().isdigit()]
    if prices:
        print()
        print(f"价格区间: ${min(prices):,} – ${max(prices):,}")

    return 1 if errors else 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "现实车-游戏车映射表.csv"
    )
    sys.exit(main(target))
