import pandas as pd
import requests
import random
from requests.exceptions import RequestException
import time

# ====================== 配置项 ======================
EXCEL_FILE = "data.xlsx"
SHEET_NAME = 0
OUTPUT_FILE = "检测结果.xlsx"
TIMEOUT = 10
MIN_DELAY = 1
MAX_DELAY = 3
START_ROW = 334    # 起始行（从1开始，不含表头）
END_ROW = 871   # 结束行（None 表示读到最后一行）
# ====================================================

def check_url_contains_question(url: str, question: str) -> tuple[bool, str]:
    if pd.isna(url) or pd.isna(question):
        return False, "URL或问题为空"
    
    url = str(url).strip()
    question = str(question).strip()
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(
            url, 
            headers=headers, 
            timeout=TIMEOUT, 
            allow_redirects=True
        )
        response.raise_for_status()
        
        page_content = response.text
        contains = question in page_content
        status = "✅ 包含" if contains else "❌ 不包含"
        return contains, status

    except RequestException as e:
        return False, f"请求失败: {str(e)}"
    except Exception as e:
        return False, f"未知错误: {str(e)}"

def main():
    # 参数校验
    if START_ROW < 1:
        print("❌ 错误：START_ROW 不能小于 1")
        return
    if END_ROW is not None and END_ROW < START_ROW:
        print("❌ 错误：END_ROW 不能小于 START_ROW")
        return

    print("=" * 50)
    print("📄 按列位置读取（B列=问题，D列=链接）")
    print("🔍 不包含时自动打印问题+链接")
    if END_ROW is None:
        print(f"📌 检测范围：第 {START_ROW} 行 ～ 最后一行")
    else:
        print(f"📌 检测范围：第 {START_ROW} 行 ～ 第 {END_ROW} 行")
    print("=" * 50)
    
    try:
        df = pd.read_excel(
            EXCEL_FILE, 
            sheet_name=SHEET_NAME,
            header=None,
            skiprows=1
        )

        question_col_index = 1   # B列
        url_col_index = 3        # D列

        if len(df.columns) <= max(question_col_index, url_col_index):
            print("❌ 错误：表格至少需要4列")
            return

        # 转换为 0-based 索引后切片
        start_idx = START_ROW - 1
        end_idx = END_ROW if END_ROW is None else END_ROW

        df_slice = df.iloc[start_idx:end_idx].copy()
        df_slice = df_slice.reset_index(drop=True)

        if len(df_slice) == 0:
            print("❌ 错误：指定范围内没有数据")
            return

        df_slice["检测结果"] = ""
        df_slice["状态说明"] = ""
        
        total_rows = len(df_slice)
        print(f"✅ 本次检测行数：{total_rows}\n")

        for index, row in df_slice.iterrows():
            question = row.iloc[question_col_index]
            url = row.iloc[url_col_index]
            
            # 显示的是原始表格中的真实行号
            real_row_num = START_ROW + index
            
            contains, status = check_url_contains_question(url, question)
            
            df_slice.at[index, "检测结果"] = contains
            df_slice.at[index, "状态说明"] = status

            if status == "❌ 不包含":
                print(f"[{index+1}/{total_rows}] (第{real_row_num}行) {status}")
                print(f"   问题：{question}")
                print(f"   链接：{url}\n")
            else:
                print(f"[{index+1}/{total_rows}] (第{real_row_num}行) {status}")
            
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            time.sleep(delay)

        df_slice.to_excel(OUTPUT_FILE, index=False)
        print(f"\n🎉 检测完成！结果保存至：{OUTPUT_FILE}")

    except FileNotFoundError:
        print(f"❌ 错误：未找到文件 {EXCEL_FILE}")
    except Exception as e:
        print(f"❌ 出错：{str(e)}")

if __name__ == "__main__":
    main()