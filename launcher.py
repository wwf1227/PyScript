#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 @Time : 2025/11/25
 @Author : wwf
 Description: 
"""
import streamlit.web.cli as stcli
import sys

if __name__ == '__main__':
    sys.argv = ["streamlit", "run", "app.py", "--server.headless", "false"]
    sys.exit(stcli.main())