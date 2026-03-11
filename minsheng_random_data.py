import pandas as pd
import numpy as np

# ===== 1. 读取原始数据文件 =====
# 这里可以是 Excel 或 CSV 文件
input_file = "原始数据.xlsx"  # 或 "原始数据.csv"
sheet_name = "Sheet1"  # 如果是 Excel，需要指定 sheet

# 判断文件类型
if input_file.endswith(".xlsx") or input_file.endswith(".xls"):
    data = pd.read_excel(input_file, sheet_name=sheet_name)
else:
    data = pd.read_csv(input_file)

# ===== 2. 计算每行原始平均值 =====
data['原始平均'] = data.mean(axis=1)

# ===== 3. 生成 ±5% 浮动的新数据 =====
def generate_fluctuation(row, fluctuation=0.05):
    new_row = row.copy()
    for col in row.index[:-1]:  # 忽略最后一列平均值
        factor = 1 + np.random.uniform(-fluctuation, fluctuation)
        new_row[col] = round(row[col] * factor)
    return new_row

new_data = data.apply(generate_fluctuation, axis=1)

# ===== 4. 矫正每行平均值，保证误差 <= 20 =====
for i in range(len(data)):
    original_avg = data.loc[i, '原始平均']
    generated_avg = new_data.loc[i, '原始平均'] = new_data.iloc[i, :-1].mean()
    diff = generated_avg - original_avg
    if abs(diff) > 20:
        correction = diff / len(data.columns[:-1])
        for col in new_data.columns[:-1]:
            new_data.loc[i, col] = round(new_data.loc[i, col] - correction)
        # 更新平均值
        new_data.loc[i, '原始平均'] = new_data.iloc[i, :-1].mean()

# ===== 5. 输出生成的新数据 =====
output_file = "生成数据.xlsx"  # 或 "生成数据.csv"
if output_file.endswith(".xlsx") or output_file.endswith(".xls"):
    new_data.to_excel(output_file, index=False)
else:
    new_data.to_csv(output_file, index=False)

print(f"生成的新数据已保存到：{output_file}")