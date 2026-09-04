import pandas as pd
from datetime import date, timedelta
import chinese_calendar as cc

year = 2026
start = date(year, 1, 1)
end = date(year, 12, 31)

workdays = []
holidays = []
makeup_workdays = []  # 调休补班（周末上班）

current = start

while current <= end:
    is_workday = cc.is_workday(current)
    is_holiday = cc.is_holiday(current)
    is_weekend = current.weekday() >= 5  # 周六日

    if is_workday:
        workdays.append(current)

    if is_holiday:
        holidays.append(current)

    # 周末但要上班 = 调休
    if is_weekend and is_workday:
        makeup_workdays.append(current)

    current += timedelta(days=1)

# 转为DataFrame
df_work = pd.DataFrame(
    [d.strftime("%Y-%m-%d") for d in workdays],
    columns=["Workday"]
)

df_holiday = pd.DataFrame(
    [d.strftime("%Y-%m-%d") for d in holidays],
    columns=["Holiday"]
)

df_makeup = pd.DataFrame(
    [d.strftime("%Y-%m-%d") for d in makeup_workdays],
    columns=["Makeup Workday"]
)

# 写入 Excel 多个 Sheet
file_name = "2026_中国日历.xlsx"
with pd.ExcelWriter(file_name, engine="openpyxl") as writer:
    df_work.to_excel(writer, sheet_name="工作日", index=False)
    df_holiday.to_excel(writer, sheet_name="法定节假日", index=False)
    df_makeup.to_excel(writer, sheet_name="调休补班", index=False)

print("生成完成：", file_name)
print("工作日数量：", len(df_work))
print("节假日数量：", len(df_holiday))
print("调休上班：", len(df_makeup))