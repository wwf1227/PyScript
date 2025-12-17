#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/12/10
 @Author : wwf
 Description: 
"""
import pandas as pd

# 读取 Excel
df = pd.read_excel("开奖数据25.xlsx")


# ===============================
# 通用连续段查找函数
# ===============================
def find_streak_ranges(series, target, df):
    streaks = []
    start_idx = None
    current = 0

    for i, v in enumerate(series):
        if v == target:
            if start_idx is None:
                start_idx = i
            current += 1
        else:
            if start_idx is not None:
                streaks.append((start_idx, i - 1, current))
                start_idx = None
                current = 0

    if start_idx is not None:
        streaks.append((start_idx, len(series) - 1, current))

    return streaks


def to_readable(ranges, df):
    readable = []
    for s in ranges:
        start_row = df.iloc[s[0]]
        end_row = df.iloc[s[1]]
        readable.append({
            "连续期数": s[2],
            "开始期数": start_row["期数"],
            "结束期数": end_row["期数"],
            "开始时间": start_row["开奖时间"],
            "结束时间": end_row["开奖时间"],
        })
    return readable


# ===============================
# 用于分析任意分类列（如 大/小、单/双）
# ===============================
def analyze_series(series, target, df):
    streaks = find_streak_ranges(series, target, df)

    if not streaks:
        return None, None, None

    max_len = max(s[2] for s in streaks)
    max_ranges = [s for s in streaks if s[2] == max_len]
    ge5_ranges = [s for s in streaks if s[2] >= 5]

    return (
        max_len,
        to_readable(max_ranges, df),
        to_readable(ge5_ranges, df),
    )


# ===============================
# 1. 分析冠亚和（直接使用原表列）
# ===============================
col_dx = "冠亚和大、小"
col_ds = "冠亚和单、双"

targets = {
    "冠亚和大": (df[col_dx], "大"),
    "冠亚和小": (df[col_dx], "小"),
    "冠亚和单": (df[col_ds], "单"),
    "冠亚和双": (df[col_ds], "双"),
}

print("\n==================== 冠亚和连续分析 ====================\n")


for name, (series, target) in targets.items():
    max_len, max_ranges, ge5_ranges = analyze_series(series, target, df)

    print(f"\n【{name}】最长连续：{max_len} 期")

    for r in max_ranges:
        print(f"  - 连续 {r['连续期数']} 期："
              f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")

    print(f"  【{name}】连续 ≥5 期出现次数：{len(ge5_ranges)} 次")
    for r in ge5_ranges:
        print(f"    - 连续 {r['连续期数']} 期："
              f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")

    print()


# ===============================
# 2. 分析号码1～号码10（自动分类 大/小，单/双）
# ===============================

# def num_big_small(n):
#     return "大" if n > 5 else "小"
#
#
# def num_odd_even(n):
#     return "双" if n % 2 == 0 else "单"
#
#
# number_cols = [f"号码{i}" for i in range(1, 11)]
#
# print("\n==================== 号码1～10连续分析 ====================\n")
#
# for col in number_cols:
#     # 动态生成大小/单双列
#     df[col + "_大小"] = df[col].apply(num_big_small)
#     df[col + "_单双"] = df[col].apply(num_odd_even)
#
#     # 分析号码大小
#     for target in ["大", "小"]:
#         series = df[col + "_大小"]
#         name = f"{col}（{target}）"
#         max_len, max_ranges, ge5_ranges = analyze_series(series, target, df)
#
#         print(f"\n【{name}】最长连续：{max_len} 期")
#         for r in max_ranges:
#             print(f"  - 连续 {r['连续期数']} 期："
#                   f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")
#
#         print(f"  【{name}】连续 ≥5 期出现次数：{len(ge5_ranges)} 次")
#         for r in ge5_ranges:
#             print(f"    - 连续 {r['连续期数']} 期："
#                   f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")
#
#     # 分析号码单双
#     for target in ["单", "双"]:
#         series = df[col + "_单双"]
#         name = f"{col}（{target}）"
#         max_len, max_ranges, ge5_ranges = analyze_series(series, target, df)
#
#         print(f"\n【{name}】最长连续：{max_len} 期")
#         for r in max_ranges:
#             print(f"  - 连续 {r['连续期数']} 期："
#                   f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")
#
#         print(f"  【{name}】连续 ≥5 期出现次数：{len(ge5_ranges)} 次")
#         for r in ge5_ranges:
#             print(f"    - 连续 {r['连续期数']} 期："
#                   f"{r['开始期数']}（{r['开始时间']}） → {r['结束期数']}（{r['结束时间']}）")
#
#     print("\n" + "-" * 80 + "\n")
