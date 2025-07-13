"""
暗号化ユーティリティ
"""
from cryptography.fernet import Fernet
import os

# 暗号化キーを環境変数から取得、なければ生成
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    """データを暗号化"""
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """データを復号化"""
    try:
        return fernet.decrypt(encrypted_data.encode()).decode()
    except:
        # 復号化に失敗した場合は元のデータを返す（暗号化されていない可能性）
        return encrypted_data