import itertools

# 定义关键字符和只能出现一次的字符
chars = ["10", "2", "901", "02", "."]
unique_chars = ["w", "wei", "wwf"]  # 示例：只能出现一次的字符

# 将两者结合
all_chars = chars + unique_chars


# 检查密码是否有效
def is_valid_password(password):
    # 判断长度是否大于等于4
    if len(password) < 4:
        return False
    # 判断点号是否在开头或中间
    if "." in password and (
        password.startswith(".")
        or any(password[i] == "." for i in range(len(password) - 1))
    ):
        return False
    # 如果密码中有字母，确保密码以字母开头
    if any(c.isalpha() for c in password) and not password[0].isalpha():
        return False
    # 检查 unique_chars 是否只出现一次
    if any(password.count(char) > 1 for char in unique_chars):
        return False
    return True


# 生成所有可能的组合
def generate_combinations():
    combinations = set()
    for r in range(2,len(all_chars) + 1):
        for combo in itertools.permutations(all_chars, r):
            password = "".join(combo)
            if is_valid_password(password):
                combinations.add(password)
    return combinations

# 生成所有4位数的数字密码
def generate_numeric_passwords():
    numeric_combinations = set()
    for combo in itertools.product('0123456789', repeat=4):
        password = ''.join(combo)
        numeric_combinations.add(password)
    return numeric_combinations

if __name__ == "__main__":
    combinations = generate_combinations()
    # numeric_passwords = generate_numeric_passwords()

    # 保存到文件
    with open("password.txt", "w") as f:
        for password in sorted(combinations):
            f.write(password + "\n")

    print("密码已保存到 password.txt")
