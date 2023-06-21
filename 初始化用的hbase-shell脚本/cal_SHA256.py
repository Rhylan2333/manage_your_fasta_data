import hashlib

def get_hash(in_str):
    sha256 = hashlib.sha256()
    sha256.update(in_str.encode('utf-8'))
    return sha256.hexdigest()

in_str = input("请输入你的字符串，我会计算它的 SHA256 值：\n")

print("它的 SHA256 值如下：")
print(get_hash(in_str))

