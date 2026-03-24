#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/10/11
 @Author : wwf
 Description: 
"""
import logging
from termcolor import colored
import sys


class Logger:
    def __init__(self, log_file=None):
        # 创建日志器
        self.logger = logging.getLogger("VideoDownloader")
        self.logger.setLevel(logging.DEBUG)

        # 创建控制台输出 handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)

        # 创建文件输出 handler（如果提供了日志文件路径）
        if log_file:
            fh = logging.FileHandler(log_file)
            fh.setLevel(logging.DEBUG)
            self.logger.addHandler(fh)

        # 创建格式化器
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        # 将 handler 添加到 logger
        self.logger.addHandler(ch)

    def log(self, message, level="INFO"):
        """根据日志级别打印信息"""
        if level == "INFO":
            self.logger.info(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
        elif level == "DEBUG":
            self.logger.debug(message)

    def log_exception(self, exception_message):
        """捕获异常并以红色打印"""
        error_message = colored(exception_message, "red")
        self.logger.error(error_message)


# 示例：使用 Logger
# logger = Logger()  # 不传参数则只打印到控制台
# logger = Logger("video_download.log")  # 如果需要日志文件输出，取消注释这一行并指定文件路径

if __name__ == '__main__':
    price = 1000
    price-=10
    price+=11
    print(price)
    # pass
    # logger = Logger("video_download.log")
    # logger.log("INFO", f"开始下载视频: url 到 save_path")
    #
    # logger.log_exception(str("e 始下载 始下载 始下载"))
