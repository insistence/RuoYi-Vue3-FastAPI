import bcrypt


class PwdUtil:
    """
    密码工具类
    """

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """
        工具方法：校验当前输入的密码与数据库存储的密码是否一致

        :param plain_password: 当前输入的密码
        :param hashed_password: 数据库存储的密码
        :return: 校验结果
        """
        return (
            bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8')) if hashed_password else None
        )

    @classmethod
    def get_password_hash(cls, input_password: str) -> str:
        """
        工具方法：对当前输入的密码进行加密

        :param input_password: 输入的密码
        :return: 加密成功的密码
        """
        return bcrypt.hashpw(input_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
