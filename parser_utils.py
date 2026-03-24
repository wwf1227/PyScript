#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from typing import List, Tuple, Dict


class LogParser:
    """
    日志解析工具类（最终版）

    支持：
    - 问题是 / 问题为（兼容时间前缀）
    - 答案 / 第X遍结果
    - URL清洗
    - 去重（保序）
    """

    # ⭐ 问题匹配（核心优化点）
    QUESTION_RE = re.compile(r'问题[是为][:：]\s*([^\n]+)')

    # ⭐ 两种答案来源
    ANSWER_RE = re.compile(r'答案[:：]\s*(https?://\S+)', re.IGNORECASE)
    ROUND_RE = re.compile(r'第\d+遍结果[:：]\s*(https?://\S+)', re.IGNORECASE)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """清洗URL尾部符号"""
        return url.strip().strip('.,;:!?)>"\'）】》]')

    @staticmethod
    def _normalize_question(q: str) -> str:
        """清洗问题文本"""
        return q.strip().strip('。.!！?？')

    @staticmethod
    def _deduplicate_keep_order(items: List[str]) -> List[str]:
        """去重 + 保持顺序"""
        return list(dict.fromkeys(items))

    @classmethod
    def extract_question_and_answers(
        cls,
        text: str,
        deduplicate: bool = True
    ) -> Tuple[str, List[str]]:
        """
        提取问题 + URL列表
        """

        question = None
        answers = []

        for line in text.splitlines():
            line = line.strip()

            # ⭐ 提取问题（只取第一个）
            if not question:
                m = cls.QUESTION_RE.search(line)
                if m:
                    question = cls._normalize_question(m.group(1))

            # ⭐ 匹配“答案”
            m1 = cls.ANSWER_RE.search(line)
            if m1:
                answers.append(cls._normalize_url(m1.group(1)))
                continue

            # ⭐ 匹配“第X遍结果”
            m2 = cls.ROUND_RE.search(line)
            if m2:
                answers.append(cls._normalize_url(m2.group(1)))

        if deduplicate:
            answers = cls._deduplicate_keep_order(answers)

        return question, answers

    @classmethod
    def extract_as_dict(
        cls,
        text: str,
        deduplicate: bool = True
    ) -> Dict:
        """
        推荐使用：返回结构化数据
        """

        question, answers = cls.extract_question_and_answers(
            text,
            deduplicate=deduplicate
        )

        return {
            "question": question,
            "answers": answers,
            "count": len(answers)
        }

    @classmethod
    def extract_from_json(
        cls,
        data: List[Dict],
        deduplicate: bool = True
    ) -> Dict:
        """
        ⭐ 从JSON日志直接提取（推荐用这个）

        Args:
            data: [{"text": "..."}]
        """

        # ⭐ 提取所有 text 并拼接
        text = "\n".join(
            item.get("text", "") for item in data
            if isinstance(item, dict)
        )

        return cls.extract_as_dict(text, deduplicate=deduplicate)
    
    @classmethod
    def aggregate_from_json_list(
        cls,
        data_list: List[List[Dict]],
        deduplicate: bool = True
    ) -> Dict:
        """
        ⭐ 汇总多个JSON日志

        Args:
            data_list: [json1, json2, json3...]

        Returns:
            {
                "questions": [],
                "answers": [],
                "count": int
            }
        """

        all_questions = []
        all_answers = []

        for data in data_list:
            result = cls.extract_from_json(data)

            if result["question"]:
                all_questions.append(result["question"])

            all_answers.extend(result["answers"])

        if deduplicate:
            all_answers = list(dict.fromkeys(all_answers))
            all_questions = list(dict.fromkeys(all_questions))

        return {
            "questions": all_questions,
            "answers": all_answers,
            "count": len(all_answers)
        }
# ⭐ 测试入口（可删）
if __name__ == "__main__":

    text = """
    2026-03-17 15:24:27: 问题是：如果预算在200元左右，氨糖软骨素一般有哪些选择？
    2026-03-17 15:24:27: 答案:https://www.doubao.com/thread/a7008df5dc7b1
    2026-03-17 15:24:27: 第2遍结果:https://www.doubao.com/thread/abdd2e60503eb
    2026-03-17 15:24:27: 第3遍结果:https://www.doubao.com/thread/a96f7f61b5648
    2026-03-17 15:24:27: 第4遍结果:https://www.doubao.com/thread/a3b98776bc9c4
    2026-03-17 15:24:27: 第5遍结果:https://www.doubao.com/thread/aa52199e65b44
    2026-03-17 15:24:27: 第6遍结果:https://www.doubao.com/thread/ab260b81146bb
    2026-03-17 15:24:27: 第7遍结果:https://www.doubao.com/thread/a4047c83e82a1
    2026-03-17 15:24:27: 第8遍结果:https://www.doubao.com/thread/a8c74bf2db5dd
    2026-03-17 15:24:27: 第9遍结果:https://www.doubao.com/thread/aa9e93400d7f5
    2026-03-17 15:24:27: 第10遍结果:https://www.doubao.com/thread/a03a072326151
    """

    result = LogParser.extract_as_dict(text)

    print("\n⭐ 问题：")
    print(result["question"])

    print("\n⭐ URL数量：", result["count"])

    print("\n⭐ URL列表：")
    for i, u in enumerate(result["answers"], 1):
        print(f"{i}. {u}")