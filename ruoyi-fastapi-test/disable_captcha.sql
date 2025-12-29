-- 用于测试环境的SQL脚本，禁用验证码功能

-- 更新验证码配置为禁用状态
UPDATE sys_config SET config_value = 'false' WHERE config_key = 'sys.account.captchaEnabled';
