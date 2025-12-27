#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐 Weapi 加密模块
实现AES和RSA加密
"""

import json
import random
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import rsa


# 网易云RSA公钥
MODULUS = "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
NONCE = "0CoJUm6Qyw8W8jud"
PUBKEY = "010001"
VI = "0102030405060708"


def create_secret_key(length=16):
    """生成随机secret key"""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return ''.join(random.choice(chars) for _ in range(length))


def rsa_encode(text: str) -> str:
    """RSA加密"""
    # 文本反转
    text = text[::-1]

    # 十六进制转换
    def hex_to_dec(hex_str):
        dec = 0
        for i, c in enumerate(hex_str):
            dec += int(c, 16) * (16 ** (len(hex_str) - i - 1))
        return dec

    # 计算
    a = hex_to_dec(text.encode().hex())
    b = hex_to_dec(PUBKEY)
    c = hex_to_dec(MODULUS)

    # 模幂运算
    result = pow(a, b, c)
    result_hex = format(result, 'x')

    # 补齐256位
    if len(result_hex) < 256:
        result_hex = result_hex.zfill(256)
    else:
        result_hex = result_hex[-256:]

    return result_hex


def aes_encode(secret_data: str, secret: str = "TA3YiYCfY2dDJQgg") -> str:
    """AES加密 (CBC模式)"""
    key = secret.encode('utf-8')
    iv = VI.encode('utf-8')

    cipher = AES.new(key, AES.MODE_CBC, iv)

    # PKCS7填充
    padded_data = pad(secret_data.encode('utf-8'), AES.block_size, style='pkcs7')

    encrypted = cipher.encrypt(padded_data)

    return base64.b64encode(encrypted).decode('utf-8')


def weapi_encrypt(data: dict) -> dict:
    """
    网易云weapi加密
    data: 参数字典
    返回: 加密后的params和encSecKey
    """
    # 转换为JSON
    raw = json.dumps(data)

    # 生成随机secret key
    secret_key = create_secret_key(16)

    # 第一次AES加密
    params = aes_encode(raw, NONCE)

    # 第二次AES加密
    params = aes_encode(params, secret_key)

    # RSA加密
    enc_sec_key = rsa_encode(secret_key)

    return {
        "params": params,
        "encSecKey": enc_sec_key
    }


if __name__ == "__main__":
    # 测试
    test_data = {
        "id": "347230",
        "os": "pc",
        "lv": "-1",
        "kv": "-1",
        "tv": "-1",
        "rv": "-1",
        "yv": "-1",
        "ytv": "-1",
        "yrv": "-1",
        "csrf_token": ""
    }

    result = weapi_encrypt(test_data)
    print("Params:", result["params"][:50] + "...")
    print("EncSecKey:", result["encSecKey"])
