-- 用于测试环境的SQL脚本，禁用验证码功能

-- 更新验证码配置为禁用状态
UPDATE sys_config SET config_value = 'false' WHERE config_key = 'sys.account.captchaEnabled';

-- 如果表中没有该配置项，插入配置
INSERT INTO sys_config (config_name, config_key, config_value, config_type, create_by, create_time, remark) 
SELECT '账号自助-验证码开关', 'sys.account.captchaEnabled', 'false', 'Y', 'admin', NOW(), '是否开启验证码功能（true开启，false关闭）'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sys.account.captchaEnabled');