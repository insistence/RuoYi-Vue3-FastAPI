-- ----------------------------
-- AI模型表
-- ----------------------------
drop table if exists ai_models;
create table ai_models (
  model_id          bigint(20)      not null auto_increment    comment '模型主键',
  model_code        varchar(100)    not null                   comment '模型编码',
  model_name        varchar(100)    default null               comment '模型名称',
  provider          varchar(50)     not null                   comment '提供商',
  model_sort        int(4)          not null                   comment '显示顺序',
  api_key           varchar(255)    default null               comment 'API Key',
  base_url          varchar(255)    default null               comment 'Base URL',
  model_type        varchar(50)     default null               comment '模型类型',
  max_tokens        int(11)         default null               comment '最大输出token',
  temperature       float           default null               comment '默认温度',
  support_reasoning char(1)         default 'N'                comment '是否支持推理',
  support_images    char(1)         default 'N'                comment '是否支持图片',
  status            char(1)         default '0'                comment '模型状态',
  user_id           bigint(20)                                 comment '用户ID',
  dept_id           bigint(20)                                 comment '部门ID',
  create_by         varchar(64)     default ''                 comment '创建者',
  create_time       datetime                                   comment '创建时间',
  update_by         varchar(64)     default ''                 comment '更新者',
  update_time       datetime                                   comment '更新时间',
  remark            varchar(500)    default null               comment '备注',
  primary key (model_id)
) engine=innodb auto_increment=1 comment = 'AI模型表';


-- ----------------------------
-- AI对话配置表
-- ----------------------------
drop table if exists ai_chat_config;
create table ai_chat_config (
  chat_config_id          bigint(20)      not null auto_increment    comment '配置主键',
  user_id                 bigint(20)      not null unique            comment '用户ID',
  temperature             float           default null               comment '默认温度',
  add_history_to_context  char(1)         default '0'                comment '是否添加历史记录(0是, 1否)',
  num_history_runs        int(4)          default null               comment '历史记录条数',
  system_prompt           text            default null               comment '系统提示词',
  metrics_default_visible char(1)         default '0'                comment '默认显示指标(0是, 1否)',
  vision_enabled          char(1)         default '1'                comment '是否开启视觉(0是, 1否)',
  image_max_size_mb       int(4)          default null               comment '图片最大大小(MB)',
  create_time             datetime                                   comment '创建时间',
  update_time             datetime                                   comment '更新时间',
  primary key (chat_config_id)
) engine=innodb auto_increment=1 comment = 'AI对话配置表';
