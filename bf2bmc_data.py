#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/12/15
 @Author : wwf
 Description: 
"""
import pandas as pd

df = pd.read_excel('/Users/wwf/Desktop/区间_278.xlsx')
# print(df.head())
# 本金
principal = 0

# 当前10的下标
current_index = 0

# 持续下注多少期
index_rounds = 0
# 下注金额
bet_amount = [35, 126, 441, 1540]
# 中奖金额
win_amount = [49.5, 178.2, 623.7, 2178]


def input_int(prompt, min_val=None, max_val=None):
    while True:
        try:
            value = int(input(prompt).strip())
            if min_val is not None and value < min_val:
                print(f"❌ 不能小于 {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"❌ 不能大于 {max_val}")
                continue
            return value
        except ValueError:
            print("❌ 请输入有效的整数")


max_bet_rounds = input_int("请输入最高下注期数：", min_val=2, max_val=len(bet_amount))


def get_ten_index(row):
    # a_value = row[0]
    row_values = list(row)[5:15]
    indexes = [i for i, v in enumerate(row_values) if v == 10]
    if indexes:
        index = indexes[0] + 5
        # print(f"A列值: {a_value}，F~O列中值为10的下标: {index}")
        return index
    else:
        print("没有10")
        exit(1)


for real_idx, row in zip(df.index[1:], df.iloc[1:].itertuples(index=False)):
    if real_idx == 1:
        current_index = get_ten_index(row)
        # 获取本金
        principal = row.截止本期余额
        continue

    b_value = row[current_index]

    bet = bet_amount[index_rounds]
    principal -= bet
    df.loc[real_idx, "本期下注金额"] = bet
    if principal < 0:
        print(f"{row[0]},余额不足，下期无法投注")
        break
    # print(f"投注{bet}")
    # print(b_value)
    if b_value <= 7:
        win = win_amount[index_rounds]
        df.loc[real_idx, "本期中奖金额"] = win
        principal += win
        index_rounds = 0
        # print(f"中奖了,盈利{win}")

        current_index = get_ten_index(row)
    else:
        # print("未中奖，下标不变")
        df.loc[real_idx, "本期中奖金额"] = 0
        index_rounds += 1
        if index_rounds > max_bet_rounds - 1:
            # 处理连续四期不中逻辑
            # print(f"连续{max_bet_rounds}期不中！！！")
            current_index = get_ten_index(row)
            index_rounds = 0

    df.loc[real_idx, "截止本期余额"] = principal

    # if real_idx >= 40:
    #     break

# 保存为新表格
df.to_excel("output.xlsx", index=False)
