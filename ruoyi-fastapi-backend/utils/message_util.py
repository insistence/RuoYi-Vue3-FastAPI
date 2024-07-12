from utils.log_util import logger


def message_service(sms_code: str):
    logger.info(f'短信验证码为{sms_code}')
