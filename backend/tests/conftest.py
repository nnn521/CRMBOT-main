"""全局测试配置：在任何 app 导入前设置安全环境变量。"""

import os

# 强随机测试密钥（满足 _validate_secret 的长度与占位值检查）
os.environ.setdefault("SECRET_KEY", "test-secret-key-" + "a" * 60)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "true")
# 确保不意外读取真实 .env / 数据库
os.environ.setdefault("DATABASE_URL", "")
