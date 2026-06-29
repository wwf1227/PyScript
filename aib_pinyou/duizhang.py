import pandas as pd

# =================配置区================
excel_file = "/Users/wwf/Desktop/daa.xlsx"
sheet1_name = "Sheet1"
sheet2_name = "Sheet2"
output_diff_file = "数据差异结果.xlsx"
# 联合主键：batch_id + repeatcount + task_id
key_cols = ["batch_id", "repeatcount", "task_id"]
# ======================================

# 读取数据，batch_id、task_id强制字符串防止格式匹配失败
df1 = pd.read_excel(excel_file, sheet_name=sheet1_name, dtype={"batch_id": str, "task_id": str})
df2 = pd.read_excel(excel_file, sheet_name=sheet2_name, dtype={"batch_id": str, "task_id": str})

# 清洗列名：去除首尾空格、全部转小写，避免空格/大小写导致找不到列
df1.columns = df1.columns.str.strip().str.lower()
df2.columns = df2.columns.str.strip().str.lower()

# 打印列名方便排查
print("Sheet1所有列：", df1.columns.tolist())
print("Sheet2所有列：", df2.columns.tolist())

# 校验三张主键列必须都存在
for col in key_cols:
    if col not in df1.columns:
        raise Exception(f"【Sheet1】缺少主键列：{col}，请检查表名是否有空格、大小写错误")
    if col not in df2.columns:
        raise Exception(f"【Sheet2】缺少主键列：{col}，请检查表名是否有空格、大小写错误")

# 根据三列联合主键去重
df1 = df1.drop_duplicates(subset=key_cols, keep="first")
df2 = df2.drop_duplicates(subset=key_cols, keep="first")

# 1. 筛选各自独有的数据
key_set1 = set(df1[key_cols].apply(tuple, axis=1))
key_set2 = set(df2[key_cols].apply(tuple, axis=1))

only_s1_keys = key_set1 - key_set2
only_s2_keys = key_set2 - key_set1

df_only_sheet1 = df1[df1[key_cols].apply(tuple, axis=1).isin(only_s1_keys)]
df_only_sheet2 = df2[df2[key_cols].apply(tuple, axis=1).isin(only_s2_keys)]

# 2. 两张表都存在的主键数据，对比其他字段内容差异
common_keys = key_set1 & key_set2
df1_common = df1[df1[key_cols].apply(tuple, axis=1).isin(common_keys)].set_index(key_cols)
df2_common = df2[df2[key_cols].apply(tuple, axis=1).isin(common_keys)].set_index(key_cols)

# 对齐两张表所有列，缺失列填充空值防止报错
all_cols = list(set(df1_common.columns) | set(df2_common.columns))
df1_common = df1_common.reindex(columns=all_cols)
df2_common = df2_common.reindex(columns=all_cols)

# pandas原生对比字段差异
try:
    diff_result = df1_common.compare(df2_common, keep_shape=True, keep_equal=False)
except ValueError:
    diff_result = pd.DataFrame()

diff_result = diff_result.reset_index()

# 三类差异导出到不同sheet
with pd.ExcelWriter(output_diff_file, engine="openpyxl") as writer:
    df_only_sheet1.to_excel(writer, sheet_name="仅Sheet1存在", index=False)
    df_only_sheet2.to_excel(writer, sheet_name="仅Sheet2存在", index=False)
    diff_result.to_excel(writer, sheet_name="三主键相同但内容不同", index=False)

# 统计输出
print("===== 比对完成 =====")
print(f"仅在Sheet1的数据条数：{len(df_only_sheet1)}")
print(f"仅在Sheet2的数据条数：{len(df_only_sheet2)}")
print(f"三主键一致但其他字段不一致条数：{len(diff_result)}")
print(f"差异文件已保存：{output_diff_file}")