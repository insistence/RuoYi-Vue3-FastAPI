-- ----------------------------
-- AI模型表
-- ----------------------------
drop table if exists ai_models;
create table ai_models (
  model_id          bigserial       not null,
  model_code        varchar(100)    not null,
  model_name        varchar(100)    default null,
  provider          varchar(50)     not null,
  model_sort        int4            not null,
  api_key           varchar(255)    default null,
  base_url          varchar(255)    default null,
  model_type        varchar(50)     default null,
  max_tokens        integer         default null,
  temperature       float           default null,
  support_reasoning char(1)         default 'N',
  support_images    char(1)         default 'N',
  status            char(1)         default '0',
  user_id           bigint,
  dept_id           bigint,
  create_by         varchar(64)     default '',
  create_time       timestamp(0),
  update_by         varchar(64)     default '',
  update_time       timestamp(0),
  remark            varchar(500)    default null,
  primary key (model_id)
);
comment on table ai_models is 'AI模型表';
comment on column ai_models.model_id is '模型主键';
comment on column ai_models.model_code is '模型编码';
comment on column ai_models.model_name is '模型名称';
comment on column ai_models.provider is '提供商';
comment on column ai_models.model_sort is '显示顺序';
comment on column ai_models.api_key is 'API Key';
comment on column ai_models.base_url is 'Base URL';
comment on column ai_models.model_type is '模型类型';
comment on column ai_models.max_tokens is '最大输出token';
comment on column ai_models.temperature is '默认温度';
comment on column ai_models.support_reasoning is '是否支持推理';
comment on column ai_models.support_images is '是否支持图片';
comment on column ai_models.status is '模型状态';
comment on column ai_models.user_id is '用户ID';
comment on column ai_models.dept_id is '部门ID';
comment on column ai_models.create_by is '创建者';
comment on column ai_models.create_time is '创建时间';
comment on column ai_models.update_by is '更新者';
comment on column ai_models.update_time is '更新时间';
comment on column ai_models.remark is '备注';

-- ----------------------------
-- AI对话配置表
-- ----------------------------
drop table if exists ai_chat_config;
create table ai_chat_config (
  chat_config_id          bigserial      not null,
  user_id                 bigint         not null unique,
  temperature             float          default null,
  add_history_to_context  char(1)        default '0',
  num_history_runs        int4           default null,
  system_prompt           text           default null,
  metrics_default_visible char(1)        default '0',
  vision_enabled          char(1)        default '1',
  image_max_size_mb       int4           default null,
  create_time             timestamp(0),
  update_time             timestamp(0),
  primary key (chat_config_id)
);
comment on table ai_chat_config is 'AI对话配置表';
comment on column ai_chat_config.chat_config_id is '配置主键';
comment on column ai_chat_config.user_id is '用户ID';
comment on column ai_chat_config.temperature is '默认温度';
comment on column ai_chat_config.add_history_to_context is '是否添加历史记录(0是, 1否)';
comment on column ai_chat_config.num_history_runs is '历史记录条数';
comment on column ai_chat_config.system_prompt is '系统提示词';
comment on column ai_chat_config.metrics_default_visible is '默认显示指标(0是, 1否)';
comment on column ai_chat_config.vision_enabled is '是否开启视觉(0是, 1否)';
comment on column ai_chat_config.image_max_size_mb is '图片最大大小(MB)';
comment on column ai_chat_config.create_time is '创建时间';
comment on column ai_chat_config.update_time is '更新时间';
