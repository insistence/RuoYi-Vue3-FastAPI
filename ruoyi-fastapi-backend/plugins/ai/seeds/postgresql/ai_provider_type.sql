-- ----------------------------
-- 初始化-字典类型表数据
-- ----------------------------
insert into sys_dict_type(dict_name, dict_type, status, create_by, create_time, update_by, update_time, remark)
select 'AI模型提供商', 'ai_provider_type', '0', 'plugin:ai', current_timestamp, '', null, 'AI模型提供商列表'
where not exists (select 1 from sys_dict_type where dict_type = 'ai_provider_type');

-- ----------------------------
-- 初始化-字典数据表数据
-- ----------------------------
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 1, 'AIMLAPI', 'AIMLAPI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'AIMLAPI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'AIMLAPI');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 2, 'Anthropic', 'Anthropic', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Anthropic'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Anthropic');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 3, 'Cerebras', 'Cerebras', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Cerebras'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Cerebras');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 4, 'CerebrasOpenAI', 'CerebrasOpenAI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'CerebrasOpenAI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'CerebrasOpenAI');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 5, 'Cohere', 'Cohere', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Cohere'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Cohere');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 6, 'CometAPI', 'CometAPI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'CometAPI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'CometAPI');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 7, 'DashScope', 'DashScope', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'DashScope'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'DashScope');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 8, 'DeepInfra', 'DeepInfra', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'DeepInfra'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'DeepInfra');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 9, 'DeepSeek', 'DeepSeek', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'DeepSeek'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'DeepSeek');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 10, 'Fireworks', 'Fireworks', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Fireworks'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Fireworks');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 11, 'Google', 'Google', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Google'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Google');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 12, 'Groq', 'Groq', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Groq'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Groq');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 13, 'HuggingFace', 'HuggingFace', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'HuggingFace'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'HuggingFace');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 14, 'LangDB', 'LangDB', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'LangDB'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'LangDB');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 15, 'LiteLLM', 'LiteLLM', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'LiteLLM'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'LiteLLM');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 16, 'LiteLLMOpenAI', 'LiteLLMOpenAI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'LiteLLMOpenAI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'LiteLLMOpenAI');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 17, 'LlamaCpp', 'LlamaCpp', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'LlamaCpp'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'LlamaCpp');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 18, 'LMStudio', 'LMStudio', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'LMStudio'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'LMStudio');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 19, 'Meta', 'Meta', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Meta'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Meta');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 20, 'Mistral', 'Mistral', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Mistral'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Mistral');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 21, 'N1N', 'N1N', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'N1N'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'N1N');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 22, 'Nebius', 'Nebius', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Nebius'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Nebius');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 23, 'Nexus', 'Nexus', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Nexus'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Nexus');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 24, 'Nvidia', 'Nvidia', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Nvidia'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Nvidia');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 25, 'Ollama', 'Ollama', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Ollama'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Ollama');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 26, 'OpenAI', 'OpenAI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'OpenAI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'OpenAI');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 27, 'OpenAIResponses', 'OpenAIResponses', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'OpenAIResponses'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'OpenAIResponses');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 28, 'OpenRouter', 'OpenRouter', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'OpenRouter'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'OpenRouter');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 29, 'Perplexity', 'Perplexity', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Perplexity'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Perplexity');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 30, 'Portkey', 'Portkey', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Portkey'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Portkey');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 31, 'Requesty', 'Requesty', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Requesty'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Requesty');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 32, 'Sambanova', 'Sambanova', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Sambanova'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Sambanova');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 33, 'SiliconFlow', 'SiliconFlow', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'SiliconFlow'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'SiliconFlow');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 34, 'Together', 'Together', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Together'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Together');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 35, 'Vercel', 'Vercel', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'Vercel'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'Vercel');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 36, 'VLLM', 'VLLM', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'VLLM'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'VLLM');
insert into sys_dict_data(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, update_by, update_time, remark)
select 37, 'xAI', 'xAI', 'ai_provider_type', '', 'info', 'N', '0', 'plugin:ai', current_timestamp, '', null, 'xAI'
where not exists (select 1 from sys_dict_data where dict_type = 'ai_provider_type' and dict_value = 'xAI');
