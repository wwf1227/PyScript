#!/bin/bash

# 默认输出目录
OUTPUT_DIR="/Users/wwf/Documents/Software/7z2408-mac/tools/output"
START_LINE=1

# 检查输入参数个数
if [ "$#" -lt 2 ]; then
    echo "用法: $0 <压缩包路径> <密码列表文件> [<输出目录>] [<起始行>]"
    exit 1
fi

# 获取压缩包路径和密码列表文件
ARCHIVE="$1"
PASSWORD_FILE="$2"

# 如果提供了输出目录，更新 OUTPUT_DIR
if [ "$#" -ge 3 ]; then
    OUTPUT_DIR="$3"
fi

# 如果提供了起始行，更新 START_LINE
if [ "$#" -ge 4 ]; then
    START_LINE="$4"
fi

# 检查密码列表文件是否存在
if [ ! -f "$PASSWORD_FILE" ]; then
    echo "密码列表文件不存在: $PASSWORD_FILE"
    exit 1
fi

# 检查输出目录是否存在，若不存在则创建
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "输出目录不存在，正在创建: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
fi

# 定义7z的完整路径
SEVEN_Z_PATH="/Users/wwf/Documents/Software/7z2408-mac/7zz"

# 创建一个临时文件以存储去重后的密码
TEMP_PASSWORD_FILE=$(mktemp)

# 去重密码列表
sort -u "$PASSWORD_FILE" > "$TEMP_PASSWORD_FILE"

# 逐行读取密码文件并尝试解压
current_line=0

while IFS= read -r PASSWORD || [ -n "$PASSWORD" ]; do
    current_line=$((current_line + 1))

    # 跳过起始行之前的行
    if [ "$current_line" -lt "$START_LINE" ]; then
        continue
    fi

    # 去掉开头和结尾的空白字符
    PASSWORD=$(echo "$PASSWORD" | xargs)

    # 跳过空行
    if [ -z "$PASSWORD" ]; then
        continue
    fi

    echo "尝试密码: $PASSWORD"
    
    # 使用 7z 解压文件到指定目录
    "$SEVEN_Z_PATH" x "$ARCHIVE" -p"$PASSWORD" -o"$OUTPUT_DIR" -y > /dev/null 2>&1
    
    # 检查解压是否成功
    if [ $? -eq 0 ]; then
        echo "解压成功! 密码是: $PASSWORD"
        exit 0
    fi
done < "$TEMP_PASSWORD_FILE"

# 清理临时文件
rm "$TEMP_PASSWORD_FILE"

# 如果到这里还没有成功，说明所有密码尝试完毕
echo "所有密码尝试完毕，未找到有效密码。"
