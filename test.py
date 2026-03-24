#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/12/4
 @Author : wwf
 Description: 
"""
stss = """
问题是：经常熬夜需要遮瑕的粉底液推荐，有哪些品牌比较好？ 
2026-03-18 21:35:20: nextIndex:4 
2026-03-18 21:36:26: 获取剪切板内容：：
2026-03-18 21:36:18: 答案：https://www.doubao.com/thread/a1defeda46774 
2026-03-18 21:36:26: 等待：2000 
2026-03-18 21:36:18: 答案：https://www.doubao.com/thread/a1defeda46775 
2026-03-18 21:36:26: BACK键 
2026-03-18 21:36:18: 答案：https://www.doubao.com/thread/a1defeda46776
2026-03-17 15:24:27: 问题为：如果预算在200元左右，氨糖软骨素一般有哪些选择？
2026-03-17 15:24:27: 第1遍结果:https://www.doubao.com/thread/a7008df5dc7b1
2026-03-17 15:24:27: 第2遍结果:https://www.doubao.com/thread/abdd2e60503eb
2026-03-17 15:24:27: 第3遍结果:https://www.doubao.com/thread/a96f7f61b5648
2026-03-17 15:24:27: 第4遍结果:https://www.doubao.com/thread/a3b98776bc9c4
2026-03-17 15:24:27: 第5遍结果:https://www.doubao.com/thread/aa52199e65b44
2026-03-17 15:24:27: 第6遍结果:https://www.doubao.com/thread/ab260b81146bb
2026-03-17 15:24:27: 第7遍结果:https://www.doubao.com/thread/a4047c83e82a1
2026-03-17 15:24:27: 第8遍结果:https://www.doubao.com/thread/a1defeda46776
2026-03-17 15:24:27: 第9遍结果:https://www.doubao.com/thread/a1defeda46775 
2026-03-17 15:24:27: 第10遍结果:https://www.doubao.com/thread/a1defeda46774 
2026-03-17 15:24:27: 等待：8000
"""
from parser_utils import LogParser

data = LogParser.extract_as_dict(stss)
print(data)
