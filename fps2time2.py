#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Time : 2025/11/16
@Author : wwf
Description: 帧数转为时间
"""

# times = [
#     "07:23",
#     "07:17",
#     "07:16",
#     "07:17",
#     "07:13",
#     "07:21",
#     "07:22",
#     "07:17",
# ]

# 南京银行
# 5.19
# 5.19
# 5.26
# 5.13

# 5641.5

# 宁波银行
# 3.27
# 3.26
# 4.03
# 3.28

# 3950

# 江苏银行
# 2.22
# 2.29
# 2.28
# 2877.67
times = [
    "3.06",
    "3.00",
    "3.02",
    "3.09",
    "3.05",
]

# 4708.25 3
# 7516.75 5
# 3146.8

# 每帧的时长（秒）
FPS = 30
FRAME_MS = 1000 / FPS

ms_values = []

for t in times:
    sec, frame = map(int, t.split("."))
    ms = sec * 1000 + frame * FRAME_MS
    ms_values.append(ms)

# 如果你想要整数毫秒（四舍五入）
ms_values_rounded = [round(ms) for ms in ms_values]
# print(ms_values)
print(ms_values_rounded)

# 平均值
avg_ms = round(sum(ms_values_rounded) / len(ms_values_rounded), 2)
print(avg_ms)

# 鸿蒙
# [6800, 6733, 7300, 6967, 7133, 7067, 7000, 6900, 6733, 6833, 6767, 6733, 6900, 6800]
# 6904.71

# iOS
# 7600

# Android
# [7767, 7567, 7533, 7567, 7433, 7700, 7733, 7567]
# 7608.38
