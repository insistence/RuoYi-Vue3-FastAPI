SET TIME ZONE 'UTC';

-- ----------------------------
-- 1、部门表
-- ----------------------------
drop table if exists sys_dept;
create table sys_dept (
    dept_id bigserial,
    parent_id bigint default 0,
    ancestors varchar(50) default '',
    dept_name varchar(30) default '',
    order_num int4 default 0,
    leader varchar(20) default null,
    phone varchar(11) default null,
    email varchar(50) default null,
    status char(1) default '0',
    del_flag char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    primary key (dept_id)
);
alter sequence sys_dept_dept_id_seq restart 200;
comment on column sys_dept.dept_id is '部门id';
comment on column sys_dept.parent_id is '父部门id';
comment on column sys_dept.ancestors is '祖级列表';
comment on column sys_dept.dept_name is '部门名称';
comment on column sys_dept.order_num is '显示顺序';
comment on column sys_dept.leader is '负责人';
comment on column sys_dept.phone is '联系电话';
comment on column sys_dept.email is '邮箱';
comment on column sys_dept.status is '部门状态（0正常 1停用）';
comment on column sys_dept.del_flag is '删除标志（0代表存在 2代表删除）';
comment on column sys_dept.create_by is '创建者';
comment on column sys_dept.create_time is '创建时间';
comment on column sys_dept.update_by is '更新者';
comment on column sys_dept.update_time is '更新时间';
comment on table sys_dept is '部门表';

-- ----------------------------
-- 初始化-部门表数据
-- ----------------------------
insert into sys_dept values(100,  0,   '0',          '集团总公司',   0, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(101,  100, '0,100',      '深圳分公司', 1, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(102,  100, '0,100',      '长沙分公司', 2, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(103,  101, '0,100,101',  '研发部门',   1, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(104,  101, '0,100,101',  '市场部门',   2, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(105,  101, '0,100,101',  '测试部门',   3, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(106,  101, '0,100,101',  '财务部门',   4, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(107,  101, '0,100,101',  '运维部门',   5, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(108,  102, '0,100,102',  '市场部门',   1, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);
insert into sys_dept values(109,  102, '0,100,102',  '财务部门',   2, '年糕', '15888888888', 'niangao@qq.com', '0', '0', 'admin', current_timestamp, '', null);

-- ----------------------------
-- 2、用户信息表
-- ----------------------------
drop table if exists sys_user;
create table sys_user (
    user_id bigserial not null,
    dept_id bigint default null,
    user_name varchar(30) not null,
    nick_name varchar(30) not null,
    user_type varchar(2) default '00',
    email varchar(50) default '',
    phonenumber varchar(11) default '',
    sex char(1) default '0',
    avatar varchar(100) default '',
    time_zone varchar(64) not null default 'auto',
    password varchar(100) default '',
    status char(1) default '0',
    del_flag char(1) default '0',
    login_ip varchar(128) default '',
    login_date timestamp(3) with time zone,
    pwd_update_date timestamp(3) with time zone,
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (user_id)
);
alter sequence sys_user_user_id_seq restart 100;
comment on column sys_user.user_id is '用户ID';
comment on column sys_user.dept_id is '部门ID';
comment on column sys_user.user_name is '用户账号';
comment on column sys_user.nick_name is '用户昵称';
comment on column sys_user.user_type is '用户类型（00系统用户）';
comment on column sys_user.email is '用户邮箱';
comment on column sys_user.phonenumber is '手机号码';
comment on column sys_user.sex is '用户性别（0男 1女 2未知）';
comment on column sys_user.avatar is '头像地址';
comment on column sys_user.time_zone is '显示时区（auto跟随设备或IANA名称）';
comment on column sys_user.password is '密码';
comment on column sys_user.status is '帐号状态（0正常 1停用）';
comment on column sys_user.del_flag is '删除标志（0代表存在 2代表删除）';
comment on column sys_user.login_ip is '最后登录IP';
comment on column sys_user.login_date is '最后登录时间';
comment on column sys_user.pwd_update_date is '密码最后更新时间';
comment on column sys_user.create_by is '创建者';
comment on column sys_user.create_time is '创建时间';
comment on column sys_user.update_by is '更新者';
comment on column sys_user.update_time is '更新时间';
comment on column sys_user.remark is '备注';
comment on table sys_user is '用户信息表';

-- ----------------------------
-- 初始化-用户信息表数据
-- ----------------------------
insert into sys_user values(1,  103, 'admin',   '超级管理员', '00', 'niangao@163.com', '15888888888', '1', '', 'auto', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', current_timestamp, current_timestamp, 'admin', current_timestamp, '', null, '管理员');
insert into sys_user values(2,  105, 'niangao', '年糕', 			'00', 'niangao@qq.com',  '15666666666', '1', '', 'auto', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', current_timestamp, current_timestamp, 'admin', current_timestamp, '', null, '测试员');

-- ----------------------------
-- 3、岗位信息表
-- ----------------------------
drop table if exists sys_post;
create table sys_post (
    post_id bigserial not null,
    post_code varchar(64) not null,
    post_name varchar(50) not null,
    post_sort int4 not null,
    status char(1) not null,
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (post_id)
);
alter sequence sys_post_post_id_seq restart 5;
comment on column sys_post.post_id is '岗位ID';
comment on column sys_post.post_code is '岗位编码';
comment on column sys_post.post_name is '岗位名称';
comment on column sys_post.post_sort is '显示顺序';
comment on column sys_post.status is '状态（0正常 1停用）';
comment on column sys_post.create_by is '创建者';
comment on column sys_post.create_time is '创建时间';
comment on column sys_post.update_by is '更新者';
comment on column sys_post.update_time is '更新时间';
comment on column sys_post.remark is '备注';
comment on table sys_post is '岗位信息表';

-- ----------------------------
-- 初始化-岗位信息表数据
-- ----------------------------
insert into sys_post values(1, 'ceo',  '董事长',    1, '0', 'admin', current_timestamp, '', null, '');
insert into sys_post values(2, 'se',   '项目经理',  2, '0', 'admin', current_timestamp, '', null, '');
insert into sys_post values(3, 'hr',   '人力资源',  3, '0', 'admin', current_timestamp, '', null, '');
insert into sys_post values(4, 'user', '普通员工',  4, '0', 'admin', current_timestamp, '', null, '');

-- ----------------------------
-- 4、角色信息表
-- ----------------------------
drop table if exists sys_role;
create table sys_role (
    role_id bigserial not null,
    role_name varchar(30) not null,
    role_key varchar(100) not null,
    role_sort int4 not null,
    data_scope char(1) default '1',
    menu_check_strictly smallint default 1,
    dept_check_strictly smallint default 1,
    status char(1) not null,
    del_flag char(1) default '0',
    create_by varchar(64)  default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64)  default '',
    update_time timestamp(3) with time zone,
    remark varchar(500)  default null,
    primary key (role_id)
);
alter sequence sys_role_role_id_seq restart 3;
comment on column sys_role.role_id is '角色ID';
comment on column sys_role.role_name is '角色名称';
comment on column sys_role.role_key is '角色权限字符串';
comment on column sys_role.role_sort is '显示顺序';
comment on column sys_role.data_scope is '数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）';
comment on column sys_role.menu_check_strictly is '菜单树选择项是否关联显示';
comment on column sys_role.dept_check_strictly is '部门树选择项是否关联显示';
comment on column sys_role.status is '角色状态（0正常 1停用）';
comment on column sys_role.del_flag is '删除标志（0代表存在 2代表删除）';
comment on column sys_role.create_by is '创建者';
comment on column sys_role.create_time is '创建时间';
comment on column sys_role.update_by is '更新者';
comment on column sys_role.update_time is '更新时间';
comment on column sys_role.remark is '备注';
comment on table sys_role is '角色信息表';

-- ----------------------------
-- 初始化-角色信息表数据
-- ----------------------------
insert into sys_role values(1, '超级管理员',  'admin',  1, 1, 1, 1, '0', '0', 'admin', current_timestamp, '', null, '超级管理员');
insert into sys_role values(2, '普通角色',    'common', 2, 2, 1, 1, '0', '0', 'admin', current_timestamp, '', null, '普通角色');

-- ----------------------------
-- 5、菜单权限表
-- ----------------------------
drop table if exists sys_menu;
create table sys_menu (
    menu_id bigserial not null,
    menu_name varchar(50) not null,
    parent_id bigint default 0,
    order_num int4 default 0,
    path varchar(200) default '',
    component varchar(255) default null,
    query varchar(255) default null,
    route_name varchar(50) default '',
    is_frame int4 default 1,
    is_cache int4 default 0,
    menu_type char(1) default '',
    visible char(1) default '0',
    status char(1) default '0',
    perms varchar(100) default null,
    icon varchar(100) default '#',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default '',
    primary key (menu_id)
);
alter sequence sys_menu_menu_id_seq restart 2000;
comment on column sys_menu.menu_id is '菜单ID';
comment on column sys_menu.menu_name is '菜单名称';
comment on column sys_menu.parent_id is '父菜单ID';
comment on column sys_menu.order_num is '显示顺序';
comment on column sys_menu.path is '路由地址';
comment on column sys_menu.component is '组件路径';
comment on column sys_menu.query is '路由参数';
comment on column sys_menu.route_name is '路由名称';
comment on column sys_menu.is_frame is '是否为外链（0是 1否）';
comment on column sys_menu.is_cache is '是否缓存（0缓存 1不缓存）';
comment on column sys_menu.menu_type is '菜单类型（M目录 C菜单 F按钮）';
comment on column sys_menu.visible is '菜单状态（0显示 1隐藏）';
comment on column sys_menu.status is '菜单状态（0正常 1停用）';
comment on column sys_menu.perms is '权限标识';
comment on column sys_menu.icon is '菜单图标';
comment on column sys_menu.create_by is '创建者';
comment on column sys_menu.create_time is '创建时间';
comment on column sys_menu.update_by is '更新者';
comment on column sys_menu.update_time is '更新时间';
comment on column sys_menu.remark is '备注';
comment on table sys_menu is '菜单权限表';

-- ----------------------------
-- 初始化-菜单信息表数据
-- ----------------------------
-- 一级菜单
insert into sys_menu values(1,  '系统管理', 0, '1',  'system',           null, '', '', 1, 0, 'M', '0', '0', '', 'system',   'admin', current_timestamp, '', null, '系统管理目录');
insert into sys_menu values(2,  '系统监控', 0, '2',  'monitor',          null, '', '', 1, 0, 'M', '0', '0', '', 'monitor',  'admin', current_timestamp, '', null, '系统监控目录');
insert into sys_menu values(3,  '系统工具', 0, '3',  'tool',             null, '', '', 1, 0, 'M', '0', '0', '', 'tool',     'admin', current_timestamp, '', null, '系统工具目录');
insert into sys_menu values(99, '若依官网', 0, '99', 'http://ruoyi.vip', null, '', '', 0, 0, 'M', '0', '0', '', 'guide',    'admin', current_timestamp, '', null, '若依官网地址');
-- 二级菜单
insert into sys_menu values(100,  '用户管理', 1,   '1', 'user',                'system/user/index',                 '', '', 1, 0, 'C', '0', '0', 'system:user:list',                 'user',          'admin', current_timestamp, '', null, '用户管理菜单');
insert into sys_menu values(101,  '角色管理', 1,   '2', 'role',                'system/role/index',                 '', '', 1, 0, 'C', '0', '0', 'system:role:list',                 'peoples',       'admin', current_timestamp, '', null, '角色管理菜单');
insert into sys_menu values(102,  '菜单管理', 1,   '3', 'menu',                'system/menu/index',                 '', '', 1, 0, 'C', '0', '0', 'system:menu:list',                 'tree-table',    'admin', current_timestamp, '', null, '菜单管理菜单');
insert into sys_menu values(103,  '部门管理', 1,   '4', 'dept',                'system/dept/index',                 '', '', 1, 0, 'C', '0', '0', 'system:dept:list',                 'tree',          'admin', current_timestamp, '', null, '部门管理菜单');
insert into sys_menu values(104,  '岗位管理', 1,   '5', 'post',                'system/post/index',                 '', '', 1, 0, 'C', '0', '0', 'system:post:list',                 'post',          'admin', current_timestamp, '', null, '岗位管理菜单');
insert into sys_menu values(105,  '字典管理', 1,   '6', 'dict',                'system/dict/index',                 '', '', 1, 0, 'C', '0', '0', 'system:dict:list',                 'dict',          'admin', current_timestamp, '', null, '字典管理菜单');
insert into sys_menu values(106,  '参数设置', 1,   '7', 'config',              'system/config/index',               '', '', 1, 0, 'C', '0', '0', 'system:config:list',               'edit',          'admin', current_timestamp, '', null, '参数设置菜单');
insert into sys_menu values(107,  '通知公告', 1,   '8', 'notice',              'system/notice/index',               '', '', 1, 0, 'C', '0', '0', 'system:notice:list',               'message',       'admin', current_timestamp, '', null, '通知公告菜单');
insert into sys_menu values(108,  '日志管理', 1,   '9', 'log',                 '',                                  '', '', 1, 0, 'M', '0', '0', '',                                 'log',           'admin', current_timestamp, '', null, '日志管理菜单');
insert into sys_menu values(119,  '文件管理', 1,  '10', 'file',                'system/file/index',                 '', '', 1, 0, 'C', '0', '0', 'system:file:list',                 'documentation', 'admin', current_timestamp, '', null, '文件管理菜单');
insert into sys_menu values(120,  '插件管理', 1,  '11', 'plugin',              'system/plugin/index',               '', '', 1, 0, 'C', '0', '0', 'system:plugin:list',               'component',     'admin', current_timestamp, '', null, '插件管理菜单');
insert into sys_menu values(121,  '认证中心', 1,  '12', 'oauth',               '',                                  '', '', 1, 0, 'M', '0', '0', '',                                 'oauth',          'admin', current_timestamp, '', null, '统一认证中心管理');
insert into sys_menu values(109,  '在线用户', 2,   '1', 'online',              'monitor/online/index',              '', '', 1, 0, 'C', '0', '0', 'monitor:online:list',              'online',        'admin', current_timestamp, '', null, '在线用户菜单');
insert into sys_menu values(110,  '定时任务', 2,   '2', 'job',                 'monitor/job/index',                 '', '', 1, 0, 'C', '0', '0', 'monitor:job:list',                 'job',           'admin', current_timestamp, '', null, '定时任务菜单');
insert into sys_menu values(111,  '数据监控', 2,   '3', 'druid',               'monitor/druid/index',               '', '', 1, 0, 'C', '0', '0', 'monitor:druid:list',               'druid',         'admin', current_timestamp, '', null, '数据监控菜单');
insert into sys_menu values(112,  '服务监控', 2,   '4', 'server',              'monitor/server/index',              '', '', 1, 0, 'C', '0', '0', 'monitor:server:list',              'server',        'admin', current_timestamp, '', null, '服务监控菜单');
insert into sys_menu values(113,  '缓存监控', 2,   '5', 'cache',               'monitor/cache/index',               '', '', 1, 0, 'C', '0', '0', 'monitor:cache:list',               'redis',         'admin', current_timestamp, '', null, '缓存监控菜单');
insert into sys_menu values(114,  '缓存列表', 2,   '6', 'cacheList',           'monitor/cache/list',                '', '', 1, 0, 'C', '0', '0', 'monitor:cache:list',               'redis-list',    'admin', current_timestamp, '', null, '缓存列表菜单');
insert into sys_menu values(118,  '传输加密', 2,   '7', 'transportCrypto',     'monitor/transportCrypto/index',     '', '', 1, 0, 'C', '0', '0', 'monitor:transportCrypto:list',     'chart',         'admin', current_timestamp, '', null, '传输加密监控菜单');
insert into sys_menu values(122,  'OAuth审计', 2,   '8', 'oauthAudit',          'monitor/oauthAudit/index',            '', '', 1, 0, 'C', '0', '0', 'monitor:oauthAudit:list',            'form',          'admin', current_timestamp, '', null, 'OAuth 审计日志');
insert into sys_menu values(115,  '表单构建', 3,   '1', 'build',               'tool/build/index',                  '', '', 1, 0, 'C', '0', '0', 'tool:build:list',                  'build',         'admin', current_timestamp, '', null, '表单构建菜单');
insert into sys_menu values(116,  '代码生成', 3,   '2', 'gen',                 'tool/gen/index',                    '', '', 1, 0, 'C', '0', '0', 'tool:gen:list',                    'code',          'admin', current_timestamp, '', null, '代码生成菜单');
insert into sys_menu values(117,  '系统接口', 3,   '3', 'swagger',             'tool/swagger/index',                '', '', 1, 0, 'C', '0', '0', 'tool:swagger:list',                'swagger',       'admin', current_timestamp, '', null, '系统接口菜单');
-- 三级菜单
insert into sys_menu values(500,  '操作日志', 108, '1', 'operlog',    'monitor/operlog/index',    '', '', 1, 0, 'C', '0', '0', 'monitor:operlog:list',    'form',          'admin', current_timestamp, '', null, '操作日志菜单');
insert into sys_menu values(501,  '登录日志', 108, '2', 'logininfor', 'monitor/logininfor/index', '', '', 1, 0, 'C', '0', '0', 'monitor:logininfor:list', 'logininfor',    'admin', current_timestamp, '', null, '登录日志菜单');
insert into sys_menu values(502,  '客户端管理', 121, '1', 'client',             'system/oauth/client/index',           '', '', 1, 0, 'C', '0', '0', 'system:oauthClient:list',          'client',       'admin', current_timestamp, '', null, 'OAuth Client 管理');
insert into sys_menu values(503,  '资源管理', 121, '2', 'resource',            'system/oauth/resource/index',          '', '', 1, 0, 'C', '0', '0', 'system:oauthResource:list',         'resource',     'admin', current_timestamp, '', null, 'OAuth Resource 管理');
insert into sys_menu values(504,  '范围管理', 121, '3', 'scope',               'system/oauth/scope/index',             '', '', 1, 0, 'C', '0', '0', 'system:oauthScope:list',            'scope',          'admin', current_timestamp, '', null, 'OAuth Scope 管理');
insert into sys_menu values(505,  '外部会话', 121, '4', 'session',             'system/oauth/session/index',           '', '', 1, 0, 'C', '0', '0', 'system:oauthSession:list',          'session',        'admin', current_timestamp, '', null, 'OIDC SSO Session 管理');
insert into sys_menu values(506,  '外部授权', 121, '5', 'grant',               'system/oauth/grant/index',             '', '', 1, 0, 'C', '0', '0', 'system:oauthGrant:list',            'grant',    'admin', current_timestamp, '', null, 'OAuth Grant 管理');
insert into sys_menu values(507,  '签名密钥', 121, '6', 'key',                 'system/oauth/key/index',               '', '', 1, 0, 'C', '0', '0', 'system:oauthKey:list',              'key',           'admin', current_timestamp, '', null, 'OIDC Key 管理');
-- 用户管理按钮
insert into sys_menu values(1000, '用户查询', 100, '1',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1001, '用户新增', 100, '2',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1002, '用户修改', 100, '3',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1003, '用户删除', 100, '4',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1004, '用户导出', 100, '5',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:export',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1005, '用户导入', 100, '6',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:import',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1006, '重置密码', 100, '7',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:user:resetPwd',       '#', 'admin', current_timestamp, '', null, '');
-- 角色管理按钮
insert into sys_menu values(1007, '角色查询', 101, '1',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:role:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1008, '角色新增', 101, '2',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:role:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1009, '角色修改', 101, '3',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:role:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1010, '角色删除', 101, '4',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:role:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1011, '角色导出', 101, '5',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:role:export',         '#', 'admin', current_timestamp, '', null, '');
-- 菜单管理按钮
insert into sys_menu values(1012, '菜单查询', 102, '1',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:menu:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1013, '菜单新增', 102, '2',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:menu:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1014, '菜单修改', 102, '3',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:menu:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1015, '菜单删除', 102, '4',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:menu:remove',         '#', 'admin', current_timestamp, '', null, '');
-- 部门管理按钮
insert into sys_menu values(1016, '部门查询', 103, '1',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:dept:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1017, '部门新增', 103, '2',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:dept:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1018, '部门修改', 103, '3',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:dept:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1019, '部门删除', 103, '4',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:dept:remove',         '#', 'admin', current_timestamp, '', null, '');
-- 岗位管理按钮
insert into sys_menu values(1020, '岗位查询', 104, '1',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:post:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1021, '岗位新增', 104, '2',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:post:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1022, '岗位修改', 104, '3',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:post:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1023, '岗位删除', 104, '4',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:post:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1024, '岗位导出', 104, '5',  '', '', '', '', 1, 0, 'F', '0', '0', 'system:post:export',         '#', 'admin', current_timestamp, '', null, '');
-- 字典管理按钮
insert into sys_menu values(1025, '字典查询', 105, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:dict:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1026, '字典新增', 105, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:dict:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1027, '字典修改', 105, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:dict:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1028, '字典删除', 105, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:dict:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1029, '字典导出', 105, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:dict:export',         '#', 'admin', current_timestamp, '', null, '');
-- 参数设置按钮
insert into sys_menu values(1030, '参数查询', 106, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:config:query',        '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1031, '参数新增', 106, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:config:add',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1032, '参数修改', 106, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:config:edit',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1033, '参数删除', 106, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:config:remove',       '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1034, '参数导出', 106, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:config:export',       '#', 'admin', current_timestamp, '', null, '');
-- 通知公告按钮
insert into sys_menu values(1035, '公告查询', 107, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:notice:query',        '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1036, '公告新增', 107, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:notice:add',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1037, '公告修改', 107, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:notice:edit',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1038, '公告删除', 107, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:notice:remove',       '#', 'admin', current_timestamp, '', null, '');
-- 文件管理按钮
insert into sys_menu values(1061, '文件查询', 119, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1062, '文件下载', 119, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:download',       '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1063, '文件删除', 119, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1064, '文件授权', 119, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1065, '文件转移', 119, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:transfer',       '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1066, '文件恢复', 119, '6', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:restore',        '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1067, '文件清理', 119, '7', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:purge',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1068, '存储对账', 119, '8', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:file:reconcile',      '#', 'admin', current_timestamp, '', null, '');
-- 插件管理按钮
insert into sys_menu values(1069, '插件查询', 120, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:plugin:query',        '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1070, '插件修改', 120, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:plugin:edit',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1071, '插件列表', 120, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:plugin:list',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1072, '插件导出', 120, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:plugin:export',       '#', 'admin', current_timestamp, '', null, '');
-- 操作日志按钮
insert into sys_menu values(1039, '操作查询', 500, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:query',      '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1040, '操作删除', 500, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:remove',     '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1041, '日志导出', 500, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:export',     '#', 'admin', current_timestamp, '', null, '');
-- 登录日志按钮
insert into sys_menu values(1042, '登录查询', 501, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:query',   '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1043, '登录删除', 501, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:remove',  '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1044, '日志导出', 501, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:export',  '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1045, '账户解锁', 501, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:unlock',  '#', 'admin', current_timestamp, '', null, '');
-- 认证中心管理按钮
insert into sys_menu values(1073, '客户端查询', 502, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthClient:query', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1074, '客户端新增', 502, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthClient:add', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1075, '客户端修改', 502, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthClient:edit', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1076, '客户端删除', 502, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthClient:remove', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1077, '密钥轮换', 502, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthClient:rotateSecret', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1079, '资源新增', 503, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthResource:add', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1080, '资源修改', 503, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthResource:edit', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1081, '资源删除', 503, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthResource:remove', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1083, '范围新增', 504, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthScope:add', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1084, '范围修改', 504, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthScope:edit', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1085, '范围删除', 504, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthScope:remove', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1086, '会话下线', 505, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthSession:revoke', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1087, '授权撤销', 506, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthGrant:revoke', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1088, '密钥轮换', 507, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthKey:rotate', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1089, '密钥启用', 507, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthKey:activate', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1090, '密钥退役', 507, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'system:oauthKey:retire', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1091, '审计导出', 122, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:oauthAudit:export', '#', 'admin', current_timestamp, '', null, '');
-- 在线用户按钮
insert into sys_menu values(1046, '在线查询', 109, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:online:query',       '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1047, '批量强退', 109, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:online:batchLogout', '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1048, '单条强退', 109, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:online:forceLogout', '#', 'admin', current_timestamp, '', null, '');
-- 定时任务按钮
insert into sys_menu values(1049, '任务查询', 110, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:query',          '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1050, '任务新增', 110, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:add',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1051, '任务修改', 110, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:edit',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1052, '任务删除', 110, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:remove',         '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1053, '状态修改', 110, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:changeStatus',   '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1054, '任务导出', 110, '6', '#', '', '', '', 1, 0, 'F', '0', '0', 'monitor:job:export',         '#', 'admin', current_timestamp, '', null, '');
-- 代码生成按钮
insert into sys_menu values(1055, '生成查询', 116, '1', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:query',             '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1056, '生成修改', 116, '2', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:edit',              '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1057, '生成删除', 116, '3', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:remove',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1058, '导入代码', 116, '4', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:import',            '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1059, '预览代码', 116, '5', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:preview',           '#', 'admin', current_timestamp, '', null, '');
insert into sys_menu values(1060, '生成代码', 116, '6', '#', '', '', '', 1, 0, 'F', '0', '0', 'tool:gen:code',              '#', 'admin', current_timestamp, '', null, '');

-- ----------------------------
-- 6、用户和角色关联表  用户N-1角色
-- ----------------------------
drop table if exists sys_user_role;
create table sys_user_role (
    user_id bigint not null,
    role_id bigint not null,
    primary key (user_id, role_id)
);
comment on column sys_user_role.user_id is '用户ID';
comment on column sys_user_role.role_id is '角色ID';
comment on table sys_user_role is '用户和角色关联表';

-- ----------------------------
-- 初始化-用户和角色关联表数据
-- ----------------------------
insert into sys_user_role values (1, 1);
insert into sys_user_role values (2, 2);

-- ----------------------------
-- 7、角色和菜单关联表  角色1-N菜单
-- ----------------------------
drop table if exists sys_role_menu;
create table sys_role_menu (
    role_id bigint not null,
    menu_id bigint not null,
    primary key (role_id, menu_id)
);
comment on column sys_role_menu.role_id is '角色ID';
comment on column sys_role_menu.menu_id is '菜单ID';
comment on table sys_role_menu is '角色和菜单关联表';

-- ----------------------------
-- 初始化-角色和菜单关联表数据
-- ----------------------------
insert into sys_role_menu values (2, 1);
insert into sys_role_menu values (2, 2);
insert into sys_role_menu values (2, 3);
insert into sys_role_menu values (2, 100);
insert into sys_role_menu values (2, 101);
insert into sys_role_menu values (2, 102);
insert into sys_role_menu values (2, 103);
insert into sys_role_menu values (2, 104);
insert into sys_role_menu values (2, 105);
insert into sys_role_menu values (2, 106);
insert into sys_role_menu values (2, 107);
insert into sys_role_menu values (2, 108);
insert into sys_role_menu values (2, 109);
insert into sys_role_menu values (2, 110);
insert into sys_role_menu values (2, 111);
insert into sys_role_menu values (2, 112);
insert into sys_role_menu values (2, 113);
insert into sys_role_menu values (2, 114);
insert into sys_role_menu values (2, 118);
insert into sys_role_menu values (2, 119);
insert into sys_role_menu values (2, 120);
insert into sys_role_menu values (2, 115);
insert into sys_role_menu values (2, 116);
insert into sys_role_menu values (2, 117);
insert into sys_role_menu values (2, 500);
insert into sys_role_menu values (2, 501);
insert into sys_role_menu values (2, 1000);
insert into sys_role_menu values (2, 1001);
insert into sys_role_menu values (2, 1002);
insert into sys_role_menu values (2, 1003);
insert into sys_role_menu values (2, 1004);
insert into sys_role_menu values (2, 1005);
insert into sys_role_menu values (2, 1006);
insert into sys_role_menu values (2, 1007);
insert into sys_role_menu values (2, 1008);
insert into sys_role_menu values (2, 1009);
insert into sys_role_menu values (2, 1010);
insert into sys_role_menu values (2, 1011);
insert into sys_role_menu values (2, 1012);
insert into sys_role_menu values (2, 1013);
insert into sys_role_menu values (2, 1014);
insert into sys_role_menu values (2, 1015);
insert into sys_role_menu values (2, 1016);
insert into sys_role_menu values (2, 1017);
insert into sys_role_menu values (2, 1018);
insert into sys_role_menu values (2, 1019);
insert into sys_role_menu values (2, 1020);
insert into sys_role_menu values (2, 1021);
insert into sys_role_menu values (2, 1022);
insert into sys_role_menu values (2, 1023);
insert into sys_role_menu values (2, 1024);
insert into sys_role_menu values (2, 1025);
insert into sys_role_menu values (2, 1026);
insert into sys_role_menu values (2, 1027);
insert into sys_role_menu values (2, 1028);
insert into sys_role_menu values (2, 1029);
insert into sys_role_menu values (2, 1030);
insert into sys_role_menu values (2, 1031);
insert into sys_role_menu values (2, 1032);
insert into sys_role_menu values (2, 1033);
insert into sys_role_menu values (2, 1034);
insert into sys_role_menu values (2, 1035);
insert into sys_role_menu values (2, 1036);
insert into sys_role_menu values (2, 1037);
insert into sys_role_menu values (2, 1038);
insert into sys_role_menu values (2, 1039);
insert into sys_role_menu values (2, 1040);
insert into sys_role_menu values (2, 1041);
insert into sys_role_menu values (2, 1042);
insert into sys_role_menu values (2, 1043);
insert into sys_role_menu values (2, 1044);
insert into sys_role_menu values (2, 1045);
insert into sys_role_menu values (2, 1046);
insert into sys_role_menu values (2, 1047);
insert into sys_role_menu values (2, 1048);
insert into sys_role_menu values (2, 1049);
insert into sys_role_menu values (2, 1050);
insert into sys_role_menu values (2, 1051);
insert into sys_role_menu values (2, 1052);
insert into sys_role_menu values (2, 1053);
insert into sys_role_menu values (2, 1054);
insert into sys_role_menu values (2, 1055);
insert into sys_role_menu values (2, 1056);
insert into sys_role_menu values (2, 1057);
insert into sys_role_menu values (2, 1058);
insert into sys_role_menu values (2, 1059);
insert into sys_role_menu values (2, 1060);
insert into sys_role_menu values (2, 1061);
insert into sys_role_menu values (2, 1062);
insert into sys_role_menu values (2, 1063);
insert into sys_role_menu values (2, 1064);
insert into sys_role_menu values (2, 1065);
insert into sys_role_menu values (2, 1066);
insert into sys_role_menu values (2, 1067);
insert into sys_role_menu values (2, 1068);
insert into sys_role_menu values (2, 1069);
insert into sys_role_menu values (2, 1070);
insert into sys_role_menu values (2, 1071);
insert into sys_role_menu values (2, 1072);

-- ----------------------------
-- 8、角色和部门关联表  角色1-N部门
-- ----------------------------
drop table if exists sys_role_dept;
create table sys_role_dept (
    role_id bigint not null,
    dept_id bigint not null,
    primary key (role_id, dept_id)
);
comment on column sys_role_dept.role_id is '角色ID';
comment on column sys_role_dept.dept_id is '部门ID';
comment on table sys_role_dept is '角色和部门关联表';

-- ----------------------------
-- 初始化-角色和部门关联表数据
-- ----------------------------
insert into sys_role_dept values (2, 100);
insert into sys_role_dept values (2, 101);
insert into sys_role_dept values (2, 105);

-- ----------------------------
-- 9、用户与岗位关联表  用户1-N岗位
-- ----------------------------
drop table if exists sys_user_post;
create table sys_user_post (
    user_id bigint not null,
    post_id bigint not null,
    primary key (user_id, post_id)
);
comment on column sys_user_post.user_id is '用户ID';
comment on column sys_user_post.post_id is '岗位ID';
comment on table sys_user_post is '用户与岗位关联表';

-- ----------------------------
-- 初始化-用户与岗位关联表数据
-- ----------------------------
insert into sys_user_post values (1, 1);
insert into sys_user_post values (2, 2);

-- ----------------------------
-- 10、操作日志记录
-- ----------------------------
drop table if exists sys_oper_log;
create table sys_oper_log (
    oper_id bigserial not null,
    title varchar(50) default '',
    business_type int4 default 0,
    method varchar(100) default '',
    request_method varchar(10) default '',
    operator_type int4 default 0,
    oper_name varchar(50) default '',
    dept_name varchar(50) default '',
    oper_url varchar(255) default '',
    oper_ip varchar(128) default '',
    oper_location varchar(255) default '',
    oper_param varchar(2000) default '',
    json_result varchar(2000) default '',
    status int4 default 0,
    error_msg varchar(2000) default '',
    oper_time timestamp(3) with time zone,
    cost_time bigint default 0,
    primary key (oper_id)
);
alter sequence sys_oper_log_oper_id_seq restart 100;
create index idx_sys_oper_log_bt on sys_oper_log(business_type);  
create index idx_sys_oper_log_s on sys_oper_log(status);  
create index idx_sys_oper_log_ot on sys_oper_log(oper_time);
comment on column sys_oper_log.oper_id is '日志主键';
comment on column sys_oper_log.title is '模块标题';
comment on column sys_oper_log.business_type is '业务类型（0其它 1新增 2修改 3删除）';
comment on column sys_oper_log.method is '方法名称';
comment on column sys_oper_log.request_method is '请求方式';
comment on column sys_oper_log.operator_type is '操作类别（0其它 1后台用户 2手机端用户）';
comment on column sys_oper_log.oper_name is '操作人员';
comment on column sys_oper_log.dept_name is '部门名称';
comment on column sys_oper_log.oper_url is '请求URL';
comment on column sys_oper_log.oper_ip is '主机地址';
comment on column sys_oper_log.oper_location is '操作地点';
comment on column sys_oper_log.oper_param is '请求参数';
comment on column sys_oper_log.json_result is '返回参数';
comment on column sys_oper_log.status is '操作状态（0正常 1异常）';
comment on column sys_oper_log.error_msg is '错误消息';
comment on column sys_oper_log.oper_time is '操作时间';
comment on column sys_oper_log.cost_time is '消耗时间';
comment on table sys_oper_log is '操作日志记录';

-- ----------------------------
-- 11、字典类型表
-- ----------------------------
drop table if exists sys_dict_type;
create table sys_dict_type (
    dict_id bigserial not null,
    dict_name varchar(100) default '',
    dict_type varchar(100) unique default '',
    status char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (dict_id)
);
alter sequence sys_dict_type_dict_id_seq restart 100;
comment on column sys_dict_type.dict_id is '字典主键';
comment on column sys_dict_type.dict_name is '字典名称';
comment on column sys_dict_type.dict_type is '字典类型';
comment on column sys_dict_type.status is '状态（0正常 1停用）';
comment on column sys_dict_type.create_by is '创建者';
comment on column sys_dict_type.create_time is '创建时间';
comment on column sys_dict_type.update_by is '更新者';
comment on column sys_dict_type.update_time is '更新时间';
comment on column sys_dict_type.remark is '备注';
comment on table sys_dict_type is '字典类型表';

-- ----------------------------
-- 初始化-字典类型表数据
-- ----------------------------
insert into sys_dict_type values(1,  '用户性别',     'sys_user_sex',        '0', 'admin', current_timestamp, '', null, '用户性别列表');
insert into sys_dict_type values(2,  '菜单状态',     'sys_show_hide',       '0', 'admin', current_timestamp, '', null, '菜单状态列表');
insert into sys_dict_type values(3,  '系统开关',     'sys_normal_disable',  '0', 'admin', current_timestamp, '', null, '系统开关列表');
insert into sys_dict_type values(4,  '任务状态',     'sys_job_status',      '0', 'admin', current_timestamp, '', null, '任务状态列表');
insert into sys_dict_type values(5,  '调度存储',     'sys_job_store',       '0', 'admin', current_timestamp, '', null, '调度存储列表');
insert into sys_dict_type values(6,  '任务执行器',   'sys_job_executor',    '0', 'admin', current_timestamp, '', null, '任务执行器列表');
insert into sys_dict_type values(7,  '系统是否',     'sys_yes_no',          '0', 'admin', current_timestamp, '', null, '系统是否列表');
insert into sys_dict_type values(8,  '通知类型',     'sys_notice_type',     '0', 'admin', current_timestamp, '', null, '通知类型列表');
insert into sys_dict_type values(9,  '通知状态', 	 'sys_notice_status',   '0', 'admin', current_timestamp, '', null, '通知状态列表');
insert into sys_dict_type values(10,  '操作类型', 	 'sys_oper_type',       '0', 'admin', current_timestamp, '', null, '操作类型列表');
insert into sys_dict_type values(11, '系统状态',     'sys_common_status',   '0', 'admin', current_timestamp, '', null, '登录状态列表');
insert into sys_dict_type values(12, '插件操作类型', 'plugin_operation_type', '0', 'admin', current_timestamp, '', null, '插件操作类型列表');

-- ----------------------------
-- 12、字典数据表
-- ----------------------------
drop table if exists sys_dict_data;
create table sys_dict_data (
    dict_code bigserial not null,
    dict_sort int4 default 0,
    dict_label varchar(100) default '',
    dict_value varchar(100) default '',
    dict_type varchar(100) default '',
    css_class varchar(100) default null,
    list_class varchar(100) default null,
    is_default char(1) default 'N',
    status char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (dict_code)
);
alter sequence sys_dict_data_dict_code_seq restart 100;
comment on column sys_dict_data.dict_code is '字典编码';
comment on column sys_dict_data.dict_sort is '字典排序';
comment on column sys_dict_data.dict_label is '字典标签';
comment on column sys_dict_data.dict_value is '字典键值';
comment on column sys_dict_data.dict_type is '字典类型';
comment on column sys_dict_data.css_class is '样式属性（其他样式扩展）';
comment on column sys_dict_data.list_class is '表格回显样式';
comment on column sys_dict_data.is_default is '是否默认（Y是 N否）';
comment on column sys_dict_data.status is '状态（0正常 1停用）';
comment on column sys_dict_data.create_by is '创建者';
comment on column sys_dict_data.create_time is '创建时间';
comment on column sys_dict_data.update_by is '更新者';
comment on column sys_dict_data.update_time is '更新时间';
comment on column sys_dict_data.remark is '备注';
comment on table sys_dict_data is '字典数据表';

-- ----------------------------
-- 初始化-字典数据表数据
-- ----------------------------
insert into sys_dict_data values(1,  1,  '男',               '0',             'sys_user_sex',        '',   '',        'Y', '0', 'admin', current_timestamp, '', null, '性别男');
insert into sys_dict_data values(2,  2,  '女',               '1',             'sys_user_sex',        '',   '',        'N', '0', 'admin', current_timestamp, '', null, '性别女');
insert into sys_dict_data values(3,  3,  '未知',             '2',             'sys_user_sex',        '',   '',        'N', '0', 'admin', current_timestamp, '', null, '性别未知');
insert into sys_dict_data values(4,  1,  '显示',             '0',             'sys_show_hide',       '',   'primary', 'Y', '0', 'admin', current_timestamp, '', null, '显示菜单');
insert into sys_dict_data values(5,  2,  '隐藏',             '1',             'sys_show_hide',       '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '隐藏菜单');
insert into sys_dict_data values(6,  1,  '正常',             '0',             'sys_normal_disable',  '',   'primary', 'Y', '0', 'admin', current_timestamp, '', null, '正常状态');
insert into sys_dict_data values(7,  2,  '停用',             '1',             'sys_normal_disable',  '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '停用状态');
insert into sys_dict_data values(8,  1,  '正常',             '0',              'sys_job_status',      '',   'primary', 'Y', '0', 'admin', current_timestamp, '', null, '正常状态');
insert into sys_dict_data values(9,  2,  '暂停',             '1',              'sys_job_status',      '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '停用状态');
insert into sys_dict_data values(10, 1,  '内存',             'default',        'sys_job_store',       '',   '',        'Y', '0', 'admin', current_timestamp, '', null, '内存调度存储');
insert into sys_dict_data values(11, 2,  '数据库',           'sqlalchemy',     'sys_job_store',       '',   '',        'N', '0', 'admin', current_timestamp, '', null, '数据库调度存储');
insert into sys_dict_data values(12, 3,  'Redis',            'redis',          'sys_job_store',       '',   '',        'N', '0', 'admin', current_timestamp, '', null, 'Redis调度存储');
insert into sys_dict_data values(13, 1,  '默认',             'default',  		'sys_job_executor',    '',   '',        'N', '0', 'admin', current_timestamp, '', null, '异步函数在事件循环运行，同步函数在线程池运行');
insert into sys_dict_data values(14, 2,  '进程池',           'processpool',     'sys_job_executor',    '',   '',        'N', '0', 'admin', current_timestamp, '', null, '进程池');
insert into sys_dict_data values(15, 1,  '是',               'Y',       		'sys_yes_no',          '',   'primary', 'Y', '0', 'admin', current_timestamp, '', null, '系统默认是');
insert into sys_dict_data values(16, 2,  '否',               'N',       		'sys_yes_no',          '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '系统默认否');
insert into sys_dict_data values(17, 1,  '通知',             '1',       		'sys_notice_type',     '',   'warning', 'Y', '0', 'admin', current_timestamp, '', null, '通知');
insert into sys_dict_data values(18, 2,  '公告',             '2',       		'sys_notice_type',     '',   'success', 'N', '0', 'admin', current_timestamp, '', null, '公告');
insert into sys_dict_data values(19, 1,  '正常',             '0',       		'sys_notice_status',   '',   'primary', 'Y', '0', 'admin', current_timestamp, '', null, '正常状态');
insert into sys_dict_data values(20, 2,  '关闭',             '1',       		'sys_notice_status',   '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '关闭状态');
insert into sys_dict_data values(21, 99, '其他',             '0',       		'sys_oper_type',       '',   'info',    'N', '0', 'admin', current_timestamp, '', null, '其他操作');
insert into sys_dict_data values(22, 1,  '新增',             '1',       		'sys_oper_type',       '',   'info',    'N', '0', 'admin', current_timestamp, '', null, '新增操作');
insert into sys_dict_data values(23, 2,  '修改',             '2',       		'sys_oper_type',       '',   'info',    'N', '0', 'admin', current_timestamp, '', null, '修改操作');
insert into sys_dict_data values(24, 3,  '删除',             '3',       		'sys_oper_type',       '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '删除操作');
insert into sys_dict_data values(25, 4,  '授权',             '4',       		'sys_oper_type',       '',   'primary', 'N', '0', 'admin', current_timestamp, '', null, '授权操作');
insert into sys_dict_data values(26, 5,  '导出',             '5',       		'sys_oper_type',       '',   'warning', 'N', '0', 'admin', current_timestamp, '', null, '导出操作');
insert into sys_dict_data values(27, 6,  '导入',             '6',       		'sys_oper_type',       '',   'warning', 'N', '0', 'admin', current_timestamp, '', null, '导入操作');
insert into sys_dict_data values(28, 7,  '强退',             '7',       		'sys_oper_type',       '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '强退操作');
insert into sys_dict_data values(29, 8,  '生成代码',          '8',       		 'sys_oper_type',       '',   'warning', 'N', '0', 'admin', current_timestamp, '', null, '生成操作');
insert into sys_dict_data values(30, 9,  '清空数据',          '9',       		 'sys_oper_type',       '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '清空操作');
insert into sys_dict_data values(31, 1,  '成功',             '0',       		'sys_common_status',   '',   'primary', 'N', '0', 'admin', current_timestamp, '', null, '正常状态');
insert into sys_dict_data values(32, 2,  '失败',             '1',       		'sys_common_status',   '',   'danger',  'N', '0', 'admin', current_timestamp, '', null, '停用状态');
insert into sys_dict_data values(33, 1,   '安装',            'install',          'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件安装');
insert into sys_dict_data values(34, 2,   '启用',            'enable',           'plugin_operation_type', '',  'success', 'N', '0', 'admin', current_timestamp, '', null, '插件启用');
insert into sys_dict_data values(35, 3,   '停用',            'disable',          'plugin_operation_type', '',  'warning', 'N', '0', 'admin', current_timestamp, '', null, '插件停用');
insert into sys_dict_data values(36, 4,   '升级',            'upgrade',          'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件升级');
insert into sys_dict_data values(37, 5,   '卸载',            'uninstall',        'plugin_operation_type', '',  'danger',  'N', '0', 'admin', current_timestamp, '', null, '插件卸载');
insert into sys_dict_data values(38, 6,   '清理',            'purge',            'plugin_operation_type', '',  'danger',  'N', '0', 'admin', current_timestamp, '', null, '插件清理');
insert into sys_dict_data values(39, 7,   '批量',            'batch',            'plugin_operation_type', '',  'info',    'N', '0', 'admin', current_timestamp, '', null, '插件批量操作');
insert into sys_dict_data values(40, 8,   '批量安装',         'batch_install',    'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件批量安装');
insert into sys_dict_data values(41, 9,   '批量启用',         'batch_enable',     'plugin_operation_type', '',  'success', 'N', '0', 'admin', current_timestamp, '', null, '插件批量启用');
insert into sys_dict_data values(42, 10,  '批量升级',         'batch_upgrade',    'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件批量升级');
insert into sys_dict_data values(43, 11,  '配置保存',         'config_set',       'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件配置保存');
insert into sys_dict_data values(44, 12,  '配置更新',         'config_update',    'plugin_operation_type', '',  'primary', 'N', '0', 'admin', current_timestamp, '', null, '插件配置更新');
insert into sys_dict_data values(45, 13,  '配置导入',         'config_import',    'plugin_operation_type', '',  'warning', 'N', '0', 'admin', current_timestamp, '', null, '插件配置导入');
insert into sys_dict_data values(46, 14,  '配置导出',         'config_export',    'plugin_operation_type', '',  'warning', 'N', '0', 'admin', current_timestamp, '', null, '插件配置导出');
insert into sys_dict_data values(47, 99,  '未知操作',         'unknown',          'plugin_operation_type', '',  'info',    'N', '0', 'admin', current_timestamp, '', null, '插件未知操作');

-- ----------------------------
-- 13、参数配置表
-- ----------------------------
drop table if exists sys_config;
create table sys_config (
    config_id serial not null,
    config_name varchar(100) default '',
    config_key varchar(100) default '',
    config_value varchar(500) default '',
    config_type char(1) default 'N',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (config_id)
);
alter sequence sys_config_config_id_seq restart 100;
comment on column sys_config.config_id is '参数主键';
comment on column sys_config.config_name is '参数名称';
comment on column sys_config.config_key is '参数键名';
comment on column sys_config.config_value is '参数键值';
comment on column sys_config.config_type is '系统内置（Y是 N否）';
comment on column sys_config.create_by is '创建者';
comment on column sys_config.create_time is '创建时间';
comment on column sys_config.update_by is '更新者';
comment on column sys_config.update_time is '更新时间';
comment on column sys_config.remark is '备注';
comment on table sys_config is '参数配置表';

-- ----------------------------
-- 初始化-参数配置表数据
-- ----------------------------
insert into sys_config values(1, '主框架页-默认皮肤样式名称',     'sys.index.skinName',            'skin-blue',     'Y', 'admin', current_timestamp, '', null, '蓝色 skin-blue、绿色 skin-green、紫色 skin-purple、红色 skin-red、黄色 skin-yellow' );
insert into sys_config values(2, '用户管理-账号初始密码',         'sys.user.initPassword',         '123456',        'Y', 'admin', current_timestamp, '', null, '初始化密码 123456' );
insert into sys_config values(3, '主框架页-侧边栏主题',           'sys.index.sideTheme',           'theme-dark',    'Y', 'admin', current_timestamp, '', null, '深色主题theme-dark，浅色主题theme-light' );
insert into sys_config values(4, '账号自助-验证码开关',           'sys.account.captchaEnabled',    'true',          'Y', 'admin', current_timestamp, '', null, '是否开启验证码功能（true开启，false关闭）');
insert into sys_config values(5, '账号自助-是否开启用户注册功能', 'sys.account.registerUser',      'false',         'Y', 'admin', current_timestamp, '', null, '是否开启注册用户功能（true开启，false关闭）');
insert into sys_config values(6, '用户登录-黑名单列表',           'sys.login.blackIPList',         '',              'Y', 'admin', current_timestamp, '', null, '设置登录IP黑名单限制，多个匹配项以;分隔，支持匹配（*通配、网段）');
insert into sys_config values(7, '用户管理-初始密码修改策略',     'sys.account.initPasswordModify',  '1',             'Y', 'admin', current_timestamp, '', null, '0：初始密码修改策略关闭，没有任何提示，1：提醒用户，如果未修改初始密码，则在登录时就会提醒修改密码对话框');
insert into sys_config values(8, '用户管理-账号密码更新周期',     'sys.account.passwordValidateDays', '0',             'Y', 'admin', current_timestamp, '', null, '密码更新周期（填写数字，数据初始化值为0不限制，若修改必须为大于0小于365的正整数），如果超过这个周期登录系统时，则在登录时就会提醒修改密码对话框');
insert into sys_config values(9, '插件管理-操作审计保留天数',     'sys.plugin.operationLogRetentionDays', '180',       'Y', 'admin', current_timestamp, '', null, '插件操作审计日志默认保留天数，0表示清理当前时间之前的全部日志');
insert into sys_config values(10, '用户管理-密码字符范围',        'sys.account.chrtype',              '0',             'Y', 'admin', current_timestamp, '', null, '默认任意字符范围，0任意（密码可以输入任意字符），1数字（密码只能为0-9数字），2英文字母（密码只能为a-z和A-Z字母），3字母和数字（密码必须包含字母，数字）,4字母数字和特殊字符（目前支持的特殊字符包括：~!@#$%^&*()-=_+）');

-- ----------------------------
-- 14、系统访问记录
-- ----------------------------
drop table if exists sys_logininfor;
create table sys_logininfor (
    info_id bigserial not null,
    user_name varchar(50) default '',
    ipaddr varchar(128) default '',
    login_location varchar(255) default '',
    browser varchar(50) default '',
    os varchar(50) default '',
    status char(1) default '0',
    msg varchar(255) default '',
    login_time timestamp(3) with time zone,
    primary key (info_id)
);
alter sequence sys_logininfor_info_id_seq restart 100;
create index idx_sys_logininfor_s on sys_logininfor(status);  
create index idx_sys_logininfor_lt on sys_logininfor(login_time);
comment on column sys_logininfor.info_id is '访问ID';
comment on column sys_logininfor.user_name is '用户账号';
comment on column sys_logininfor.ipaddr is '登录IP地址';
comment on column sys_logininfor.login_location is '登录地点';
comment on column sys_logininfor.browser is '浏览器类型';
comment on column sys_logininfor.os is '操作系统';
comment on column sys_logininfor.status is '登录状态（0成功 1失败）';
comment on column sys_logininfor.msg is '提示消息';
comment on column sys_logininfor.login_time is '访问时间';
comment on table sys_logininfor is '系统访问记录';

-- ----------------------------
-- 15、定时任务调度表
-- ----------------------------
drop table if exists sys_job;
create table sys_job (
    job_id bigserial not null,
    job_name varchar(64) not null,
    job_group varchar(64) not null default 'default',
    job_store varchar(64) not null default 'default',
    job_executor varchar(64) default 'default',
    invoke_target varchar(500) not null,
    job_args json not null,
    job_kwargs json not null,
    cron_expression varchar(255) default '',
    time_zone varchar(64) not null,
    misfire_grace_time integer default 1,
    coalesce boolean not null default false,
    max_instances integer not null default 1,
    status char(1) not null default '1',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default '',
    primary key (job_id),
    constraint uq_job_group_name unique (job_group, job_name),
    constraint ck_job_max_instances check (max_instances >= 1),
    constraint ck_job_misfire_grace check (misfire_grace_time is null or misfire_grace_time >= 1)
);
alter sequence sys_job_job_id_seq restart 100;
comment on column sys_job.job_id is '任务ID';
comment on column sys_job.job_name is '任务名称';
comment on column sys_job.job_group is '业务分组';
comment on column sys_job.job_executor is '任务执行器';
comment on column sys_job.invoke_target is '调用目标字符串';
comment on column sys_job.job_args is '位置参数';
comment on column sys_job.job_kwargs is '关键字参数';
comment on column sys_job.cron_expression is 'cron执行表达式';
comment on column sys_job.time_zone is 'cron时区（IANA）';
comment on column sys_job.status is '状态（0正常 1暂停）';
comment on column sys_job.create_by is '创建者';
comment on column sys_job.create_time is '创建时间';
comment on column sys_job.update_by is '更新者';
comment on column sys_job.update_time is '更新时间';
comment on column sys_job.remark is '备注信息';
comment on column sys_job.job_store is '调度存储';
comment on column sys_job.misfire_grace_time is '允许延迟秒数，NULL表示不限';
comment on column sys_job.coalesce is '积压时是否只执行最近一次';
comment on column sys_job.max_instances is '任务最大并发数';
comment on table sys_job is '定时任务调度表';

-- ----------------------------
-- 初始化-定时任务调度表数据
-- ----------------------------
insert into sys_job values(1, '系统默认（无参）', 'default', 'default', 'default', 'module_task.scheduler_test.job', '[]', '{}', '0/10 * * * * ?', 'Asia/Shanghai', 1, false, 1, '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(2, '系统默认（有参）', 'default', 'default', 'default', 'module_task.scheduler_test.job', '["test"]', '{}', '0/15 * * * * ?', 'Asia/Shanghai', 1, false, 1, '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(3, '系统默认（多参）', 'default', 'default', 'default', 'module_task.scheduler_test.job', '["new"]',  '{"test": 111}', '0/20 * * * * ?', 'Asia/Shanghai', 1, false, 1, '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(4, '文件保留期限提醒', 'default', 'default', 'default', 'module_task.file_task.scan_retention_reminders', '[]', '{"remind_days": 7, "batch_size": 500}', '0 0 1 * * ?', 'Asia/Shanghai', 1, false, 1, '0', 'admin', current_timestamp, '', null, '每天扫描即将到期和已到期的受保护文件');
insert into sys_job values(5, '回收站永久清理', 'default', 'default', 'default', 'module_task.file_task.purge_recycle_bin', '[]', '{"retention_days": 30, "batch_size": 100}', '0 0 2 * * ?', 'Asia/Shanghai', 1, false, 1, '1', 'admin', current_timestamp, '', null, '永久清理超过保留期限的回收站文件，默认暂停');
insert into sys_job values(6, '文件存储对账', 'default', 'default', 'default', 'module_task.file_task.reconcile_file_storage', '[]', '{"check_hash": false}', '0 0 3 * * ?', 'Asia/Shanghai', 1, false, 1, '1', 'admin', current_timestamp, '', null, '校验文件信息表和本地存储一致性，默认暂停');

-- ----------------------------
-- 16、任务调度同步状态（删除任务后保留同步记录）
-- ----------------------------
drop table if exists sys_job_sync;
create table sys_job_sync (
    job_id bigint not null primary key,
    config_version bigint not null default 1,
    applied_version bigint not null default 0,
    config_hash varchar(64) not null,
    deleted boolean not null default false,
    sync_status varchar(16) not null default 'pending',
    sync_error varchar(2000),
    applied_time timestamp(3) with time zone,
    next_run_time timestamp(3) with time zone,
    schedule_observed_time timestamp(3) with time zone,
    create_time timestamp(3) with time zone,
    update_time timestamp(3) with time zone
);
create index ix_job_sync_status on sys_job_sync(sync_status, update_time);
comment on column sys_job_sync.next_run_time is '最近观测的实际下次调度时刻';
comment on column sys_job_sync.schedule_observed_time is 'Leader调度观测时刻';
comment on table sys_job_sync is '任务调度同步状态';
comment on column sys_job_sync.job_id is '逻辑任务ID';
comment on column sys_job_sync.config_version is '最新配置版本';
comment on column sys_job_sync.applied_version is '已应用版本';
comment on column sys_job_sync.config_hash is '最新配置摘要';
comment on column sys_job_sync.deleted is '任务是否已删除';
comment on column sys_job_sync.sync_status is 'pending/applied/failed';
comment on column sys_job_sync.sync_error is '最近同步错误';
comment on column sys_job_sync.applied_time is '最近应用时刻';
comment on column sys_job_sync.create_time is '创建时间';
comment on column sys_job_sync.update_time is '更新时间';

-- ----------------------------
-- 17、任务执行请求与状态
-- ----------------------------
drop table if exists sys_job_execution;
create table sys_job_execution (
    execution_id varchar(32) not null primary key,
    job_id bigint not null,
    source varchar(10) not null,
    status varchar(16) not null default 'pending',
    job_snapshot json not null,
    owner_token varchar(64),
    lease_until timestamp(3) with time zone,
    scheduled_time timestamp(3) with time zone,
    start_time timestamp(3) with time zone,
    end_time timestamp(3) with time zone,
    run_duration_ms bigint,
    message text,
    requested_by varchar(64),
    create_time timestamp(3) with time zone,
    update_time timestamp(3) with time zone
);
create index ix_job_execution_dispatch on sys_job_execution(status, create_time);
create index ix_job_execution_active on sys_job_execution(job_id, status);
comment on table sys_job_execution is '任务执行请求与状态';
comment on column sys_job_execution.execution_id is '执行ID';
comment on column sys_job_execution.job_id is '逻辑任务ID';
comment on column sys_job_execution.source is 'manual/cron';
comment on column sys_job_execution.status is '执行状态';
comment on column sys_job_execution.job_snapshot is '提交时任务配置快照';
comment on column sys_job_execution.owner_token is '派发或执行占用凭据';
comment on column sys_job_execution.lease_until is '执行占用租约截止时刻';
comment on column sys_job_execution.scheduled_time is '计划执行时刻';
comment on column sys_job_execution.start_time is '实际开始时刻';
comment on column sys_job_execution.end_time is '实际结束时刻';
comment on column sys_job_execution.run_duration_ms is '实际执行耗时（毫秒）';
comment on column sys_job_execution.message is '执行结果或未执行原因';
comment on column sys_job_execution.requested_by is '手动执行提交者';
comment on column sys_job_execution.create_time is '创建时间';
comment on column sys_job_execution.update_time is '更新时间';

-- ----------------------------
-- 18、定时任务调度日志表
-- ----------------------------
drop table if exists sys_job_log;
create table sys_job_log (
    job_log_id bigserial not null,
    job_id bigint,
    execution_id varchar(32),
    job_store varchar(64),
    job_name varchar(64) not null,
    job_group varchar(64) not null,
    job_executor varchar(64) not null,
    invoke_target varchar(500) not null,
    job_args json,
    job_kwargs json,
    job_trigger varchar(255) default '',
    time_zone varchar(64) default null,
    job_message varchar(500),
    status char(1) default '0',
    exception_info varchar(2000) default '',
    scheduled_time timestamp(3) with time zone default null,
    start_time timestamp(3) with time zone,
    end_time timestamp(3) with time zone,
    run_duration_ms bigint default null,
    create_time timestamp(3) with time zone,
    primary key (job_log_id)
);
create index ix_job_log_job_id on sys_job_log(job_id, create_time);
create index ix_job_log_execution_id on sys_job_log(execution_id);
comment on column sys_job_log.job_log_id is '任务日志ID';
comment on column sys_job_log.job_name is '任务名称';
comment on column sys_job_log.job_group is '任务组名';
comment on column sys_job_log.job_executor is '任务执行器';
comment on column sys_job_log.invoke_target is '调用目标字符串';
comment on column sys_job_log.job_args is '位置参数';
comment on column sys_job_log.job_kwargs is '关键字参数';
comment on column sys_job_log.job_trigger is '任务触发器';
comment on column sys_job_log.time_zone is '任务时区快照（IANA）';
comment on column sys_job_log.job_message is '日志信息';
comment on column sys_job_log.status is '执行状态（0正常 1失败）';
comment on column sys_job_log.exception_info is '异常信息';
comment on column sys_job_log.scheduled_time is '计划执行时刻';
comment on column sys_job_log.start_time is '执行开始时间';
comment on column sys_job_log.end_time is '执行结束时间';
comment on column sys_job_log.run_duration_ms is '实际执行耗时（毫秒）';
comment on column sys_job_log.create_time is '创建时间';
comment on column sys_job_log.job_id is '逻辑任务ID，历史未关联日志可为空';
comment on column sys_job_log.execution_id is '执行ID，历史未关联日志可为空';
comment on column sys_job_log.job_store is '调度存储快照';
comment on table sys_job_log is '定时任务调度日志表';

-- ----------------------------
-- 19、通知公告表
-- ----------------------------
drop table if exists sys_notice;
create table sys_notice (
    notice_id serial not null,
    notice_title varchar(50) not null,
    notice_type char(1) not null,
    notice_content bytea default null,
    status char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(255) default null,
    primary key (notice_id)
);
alter sequence sys_notice_notice_id_seq restart 10;
comment on column sys_notice.notice_id is '公告ID';
comment on column sys_notice.notice_title is '公告标题';
comment on column sys_notice.notice_type is '公告类型（1通知 2公告）';
comment on column sys_notice.notice_content is '公告内容';
comment on column sys_notice.status is '公告状态（0正常 1关闭）';
comment on column sys_notice.create_by is '创建者';
comment on column sys_notice.create_time is '创建时间';
comment on column sys_notice.update_by is '更新者';
comment on column sys_notice.update_time is '更新时间';
comment on column sys_notice.remark is '备注';
comment on table sys_notice is '通知公告表';

-- ----------------------------
-- 初始化-公告信息表数据
-- ----------------------------
insert into sys_notice values(1, '温馨提醒：2018-07-01 vfadmin新版本发布啦', '2', '新版本内容', '0', 'admin', current_timestamp, '', null, '管理员');
insert into sys_notice values(2, '维护通知：2018-07-01 vfadmin系统凌晨维护', '1', '维护内容',   '0', 'admin', current_timestamp, '', null, '管理员');

-- ----------------------------
-- 20、公告已读记录表
-- ----------------------------
drop table if exists sys_notice_read;
create table sys_notice_read (
    read_id bigserial not null,
    notice_id integer not null,
    user_id bigint not null,
    read_time timestamp(3) with time zone not null,
    primary key (read_id),
    constraint uk_user_notice unique (user_id, notice_id)
);
comment on column sys_notice_read.read_id is '已读主键';
comment on column sys_notice_read.notice_id is '公告ID';
comment on column sys_notice_read.user_id is '用户ID';
comment on column sys_notice_read.read_time is '阅读时间';
comment on table sys_notice_read is '公告已读记录表';

-- ----------------------------
-- 21、代码生成业务表
-- ----------------------------
drop table if exists gen_table;
create table gen_table (
    table_id bigserial not null,
    table_name varchar(200) default '',
    table_comment varchar(500) default '',
    data_source_name varchar(64) not null default 'primary',
    sub_table_name varchar(64) default null,
    sub_table_fk_name varchar(64) default null,
    class_name varchar(100) default '',
    tpl_category varchar(200) default 'crud',
    tpl_web_type varchar(30)  default '',
    package_name varchar(100),
    module_name varchar(30),
    business_name varchar(30),
    function_name varchar(50),
    function_author varchar(50),
    form_col_num integer default 1,
    gen_type char(1) default '0',
    gen_path varchar(200) default '/',
    options varchar(1000),
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    remark varchar(500) default null,
    primary key (table_id)
);
comment on column gen_table.table_id is '编号';
comment on column gen_table.table_name is '表名称';
comment on column gen_table.table_comment is '表描述';
comment on column gen_table.data_source_name is '目标数据源名称';
comment on column gen_table.sub_table_name is '关联子表的表名';
comment on column gen_table.sub_table_fk_name is '子表关联的外键名';
comment on column gen_table.class_name is '实体类名称';
comment on column gen_table.tpl_category is '使用的模板（crud单表操作 tree树表操作）';
comment on column gen_table.tpl_web_type is '前端模板类型（element-ui模版 element-plus模版）';
comment on column gen_table.package_name is '生成包路径';
comment on column gen_table.module_name is '生成模块名';
comment on column gen_table.business_name is '生成业务名';
comment on column gen_table.function_name is '生成功能名';
comment on column gen_table.function_author is '生成功能作者';
comment on column gen_table.form_col_num is '表单布局（单列 双列 三列）';
comment on column gen_table.gen_type is '生成代码方式（0zip压缩包 1自定义路径）';
comment on column gen_table.gen_path is '生成路径（不填默认项目路径）';
comment on column gen_table.options is '其它生成选项';
comment on column gen_table.create_by is '创建者';
comment on column gen_table.create_time is '创建时间';
comment on column gen_table.update_by is '更新者';
comment on column gen_table.update_time is '更新时间';
comment on column gen_table.remark is '备注';
comment on table gen_table is '代码生成业务表';

-- ----------------------------
-- 22、代码生成业务表字段
-- ----------------------------
drop table if exists gen_table_column;
create table gen_table_column (
    column_id bigserial not null,
    table_id bigint,
    column_name varchar(200),
    column_comment varchar(500),
    column_type varchar(100),
    python_type varchar(500),
    python_field varchar(200),
    is_pk char(1),
    is_increment char(1),
    is_required char(1),
    is_unique char(1),
    is_insert char(1),
    is_edit char(1),
    is_list char(1),
    is_query char(1),
    query_type varchar(200) default 'EQ',
    html_type varchar(200),
    dict_type varchar(200) default '',
    sort int4,
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone,
    primary key (column_id)
);
comment on column gen_table_column.column_id is '编号';
comment on column gen_table_column.table_id is '归属表编号';
comment on column gen_table_column.column_name is '列名称';
comment on column gen_table_column.column_comment is '列描述';
comment on column gen_table_column.column_type is '列类型';
comment on column gen_table_column.python_type is 'PYTHON类型';
comment on column gen_table_column.python_field is 'PYTHON字段名';
comment on column gen_table_column.is_pk is '是否主键（1是）';
comment on column gen_table_column.is_increment is '是否自增（1是）';
comment on column gen_table_column.is_required is '是否必填（1是）';
comment on column gen_table_column.is_unique is '是否唯一（1是）';
comment on column gen_table_column.is_insert is '是否为插入字段（1是）';
comment on column gen_table_column.is_edit is '是否编辑字段（1是）';
comment on column gen_table_column.is_list is '是否列表字段（1是）';
comment on column gen_table_column.is_query is '是否查询字段（1是）';
comment on column gen_table_column.query_type is '查询方式（等于、不等于、大于、小于、范围）';
comment on column gen_table_column.html_type is '显示类型（文本框、文本域、下拉框、复选框、单选框、日期控件）';
comment on column gen_table_column.dict_type is '字典类型';
comment on column gen_table_column.sort is '排序';
comment on column gen_table_column.create_by is '创建者';
comment on column gen_table_column.create_time is '创建时间';
comment on column gen_table_column.update_by is '更新者';
comment on column gen_table_column.update_time is '更新时间';
comment on table gen_table_column is '代码生成业务表字段';

-- ----------------------------
-- 23、文件信息表
-- ----------------------------
drop table if exists sys_file_info;
create table sys_file_info (
    file_id varchar(36) not null,
    original_name varchar(255) not null,
    stored_name varchar(255) not null,
    storage_key varchar(500) not null,
    storage_type varchar(20) not null default 'local',
    access_type varchar(20) not null default 'public',
    upload_user_id bigint,
    uploader_access_enabled char(1) not null default '1',
    owner_user_id bigint,
    dept_id bigint,
    acl_version integer not null default 0,
    business_type varchar(50),
    business_id varchar(64),
    extension varchar(20) not null default '',
    content_type varchar(255),
    file_size bigint not null default 0,
    file_hash varchar(64) not null,
    status varchar(20) not null default 'active',
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone not null,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone not null,
    expire_time timestamp(3) with time zone,
    deleted_time timestamp(3) with time zone,
    del_flag char(1) not null default '0',
    primary key (file_id)
);
create index idx_sys_file_info_access_status on sys_file_info(access_type, status);
create index idx_sys_file_info_owner_status on sys_file_info(owner_user_id, status);
create index idx_sys_file_info_dept_status on sys_file_info(dept_id, status);
create index idx_sys_file_info_status_deleted_time on sys_file_info(status, deleted_time);
create unique index uk_sys_file_info_storage_location on sys_file_info(storage_type, access_type, storage_key);
comment on table sys_file_info is '文件信息表';
comment on column sys_file_info.file_id is '文件ID';
comment on column sys_file_info.original_name is '原始文件名';
comment on column sys_file_info.stored_name is '存储文件名';
comment on column sys_file_info.storage_key is '存储相对路径';
comment on column sys_file_info.storage_type is '存储类型';
comment on column sys_file_info.access_type is '访问类型';
comment on column sys_file_info.upload_user_id is '上传用户ID';
comment on column sys_file_info.uploader_access_enabled is '是否保留上传人访问权限';
comment on column sys_file_info.owner_user_id is '所有者用户ID';
comment on column sys_file_info.dept_id is '所属部门ID';
comment on column sys_file_info.acl_version is '访问控制版本';
comment on column sys_file_info.business_type is '业务类型';
comment on column sys_file_info.business_id is '业务ID';
comment on column sys_file_info.extension is '文件扩展名';
comment on column sys_file_info.content_type is '内容类型';
comment on column sys_file_info.file_size is '文件大小';
comment on column sys_file_info.file_hash is '文件SHA-256';
comment on column sys_file_info.status is '文件状态';
comment on column sys_file_info.create_by is '创建者';
comment on column sys_file_info.create_time is '创建时间';
comment on column sys_file_info.update_by is '更新者';
comment on column sys_file_info.update_time is '更新时间';
comment on column sys_file_info.expire_time is '过期时间';
comment on column sys_file_info.deleted_time is '移入回收站时间';
comment on column sys_file_info.del_flag is '删除标志';

-- ----------------------------
-- 24、文件业务引用表
-- ----------------------------
drop table if exists sys_file_reference;
create table sys_file_reference (
    reference_id bigserial not null,
    file_id varchar(36) not null,
    business_type varchar(50) not null,
    business_id varchar(64) not null,
    business_name varchar(255),
    retention_expire_time timestamp(3) with time zone,
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone not null,
    primary key (reference_id)
);
create unique index uk_sys_file_reference_business on sys_file_reference(file_id, business_type, business_id);
create index idx_sys_file_reference_file on sys_file_reference(file_id);
create index idx_sys_file_reference_business on sys_file_reference(business_type, business_id);
comment on table sys_file_reference is '文件业务引用表';
comment on column sys_file_reference.reference_id is '引用ID';
comment on column sys_file_reference.file_id is '文件ID';
comment on column sys_file_reference.business_type is '业务类型';
comment on column sys_file_reference.business_id is '业务ID';
comment on column sys_file_reference.business_name is '业务名称';
comment on column sys_file_reference.retention_expire_time is '保留期限到期时间';
comment on column sys_file_reference.create_by is '创建者';
comment on column sys_file_reference.create_time is '创建时间';

-- ----------------------------
-- 25、文件业务保留策略表
-- ----------------------------
drop table if exists sys_file_retention_policy;
create table sys_file_retention_policy (
    business_type varchar(50) not null,
    retention_days integer not null,
    status char(1) not null default '0',
    remark varchar(500),
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone not null,
    update_by varchar(64) default '',
    update_time timestamp(3) with time zone not null,
    primary key (business_type)
);
comment on table sys_file_retention_policy is '文件业务保留策略表';
comment on column sys_file_retention_policy.business_type is '业务类型';
comment on column sys_file_retention_policy.retention_days is '保留天数';
comment on column sys_file_retention_policy.status is '状态（0启用 1停用）';
comment on column sys_file_retention_policy.remark is '备注';
comment on column sys_file_retention_policy.create_by is '创建者';
comment on column sys_file_retention_policy.create_time is '创建时间';
comment on column sys_file_retention_policy.update_by is '更新者';
comment on column sys_file_retention_policy.update_time is '更新时间';

-- ----------------------------
-- 26、文件保留期限提醒表
-- ----------------------------
drop table if exists sys_file_retention_notice;
create table sys_file_retention_notice (
    notice_id bigserial not null,
    file_id varchar(36) not null,
    notice_type varchar(20) not null,
    expire_time timestamp(3) with time zone not null,
    status char(1) not null default '0',
    create_time timestamp(3) with time zone not null,
    read_by varchar(64) default '',
    read_time timestamp(3) with time zone,
    primary key (notice_id)
);
create unique index uk_sys_file_retention_notice_file_type_time
    on sys_file_retention_notice(file_id, notice_type, expire_time);
create index idx_sys_file_retention_notice_file on sys_file_retention_notice(file_id);
create index idx_sys_file_retention_notice_status_time on sys_file_retention_notice(status, create_time);
comment on table sys_file_retention_notice is '文件保留期限提醒表';
comment on column sys_file_retention_notice.notice_id is '提醒ID';
comment on column sys_file_retention_notice.file_id is '文件ID';
comment on column sys_file_retention_notice.notice_type is '提醒类型';
comment on column sys_file_retention_notice.expire_time is '文件过期时间';
comment on column sys_file_retention_notice.status is '状态（0未读 1已读 2已失效）';
comment on column sys_file_retention_notice.create_time is '创建时间';
comment on column sys_file_retention_notice.read_by is '读取者';
comment on column sys_file_retention_notice.read_time is '读取时间';

-- ----------------------------
-- 27、文件访问控制表
-- ----------------------------
drop table if exists sys_file_acl;
create table sys_file_acl (
    acl_id bigserial not null,
    file_id varchar(36) not null,
    subject_type varchar(20) not null,
    subject_id bigint not null,
    permission varchar(20) not null default 'download',
    effect varchar(10) not null default 'allow',
    include_children char(1) not null default '0',
    expire_time timestamp(3) with time zone,
    create_by varchar(64) default '',
    create_time timestamp(3) with time zone not null,
    del_flag char(1) not null default '0',
    primary key (acl_id)
);
create unique index uk_sys_file_acl_subject_permission on sys_file_acl(file_id, subject_type, subject_id, permission);
create index idx_sys_file_acl_file_status on sys_file_acl(file_id, del_flag, expire_time);
create index idx_sys_file_acl_subject on sys_file_acl(subject_type, subject_id);
comment on table sys_file_acl is '文件访问控制表';
comment on column sys_file_acl.acl_id is '访问控制ID';
comment on column sys_file_acl.file_id is '文件ID';
comment on column sys_file_acl.subject_type is '主体类型';
comment on column sys_file_acl.subject_id is '主体ID';
comment on column sys_file_acl.permission is '权限类型';
comment on column sys_file_acl.effect is '授权效果';
comment on column sys_file_acl.include_children is '部门是否包含下级';
comment on column sys_file_acl.expire_time is '授权过期时间';
comment on column sys_file_acl.create_by is '创建者';
comment on column sys_file_acl.create_time is '创建时间';
comment on column sys_file_acl.del_flag is '删除标志';

-- ----------------------------
-- 28、文件访问审计表
-- ----------------------------
drop table if exists sys_file_access_log;
create table sys_file_access_log (
    audit_id bigserial not null,
    file_id varchar(36) not null,
    action varchar(20) not null,
    actor_user_id bigint,
    actor_name varchar(64) default '',
    result varchar(20) not null,
    request_id varchar(64) default '',
    trace_id varchar(64) default '',
    ip_address varchar(128) default '',
    user_agent varchar(500) default '',
    bytes_sent bigint not null default 0,
    error_message varchar(500) default '',
    operation_detail text,
    access_time timestamp(3) with time zone not null,
    primary key (audit_id)
);
create index idx_sys_file_access_log_file_time on sys_file_access_log(file_id, access_time);
create index idx_sys_file_access_log_actor_time on sys_file_access_log(actor_user_id, access_time);
comment on table sys_file_access_log is '文件访问审计表';
comment on column sys_file_access_log.audit_id is '审计ID';
comment on column sys_file_access_log.file_id is '文件ID';
comment on column sys_file_access_log.action is '操作类型';
comment on column sys_file_access_log.actor_user_id is '操作用户ID';
comment on column sys_file_access_log.actor_name is '操作用户名称';
comment on column sys_file_access_log.result is '操作结果';
comment on column sys_file_access_log.request_id is '请求ID';
comment on column sys_file_access_log.trace_id is '链路ID';
comment on column sys_file_access_log.ip_address is '客户端地址';
comment on column sys_file_access_log.user_agent is '用户代理';
comment on column sys_file_access_log.bytes_sent is '发送字节数';
comment on column sys_file_access_log.error_message is '失败原因';
comment on column sys_file_access_log.operation_detail is '操作详情';
comment on column sys_file_access_log.access_time is '访问时间';

-- ----------------------------
-- 29、文件存储对账任务表
-- ----------------------------
drop table if exists sys_file_reconcile_run;
create table sys_file_reconcile_run (
    run_id varchar(36) not null,
    trigger_type varchar(20) not null,
    status varchar(20) not null,
    check_hash char(1) not null default '0',
    lock_name varchar(32),
    scanned_file_count bigint not null default 0,
    scanned_storage_count bigint not null default 0,
    issue_count bigint not null default 0,
    new_issue_count bigint not null default 0,
    resolved_issue_count bigint not null default 0,
    started_by varchar(64) default '',
    started_time timestamp(3) with time zone not null,
    finished_time timestamp(3) with time zone,
    error_message text,
    primary key (run_id)
);
create unique index uk_sys_file_reconcile_run_lock on sys_file_reconcile_run(lock_name);
create index idx_sys_file_reconcile_run_status_time on sys_file_reconcile_run(status, started_time);
comment on table sys_file_reconcile_run is '文件存储对账任务表';
comment on column sys_file_reconcile_run.run_id is '任务ID';
comment on column sys_file_reconcile_run.trigger_type is '触发类型';
comment on column sys_file_reconcile_run.status is '任务状态';
comment on column sys_file_reconcile_run.check_hash is '是否校验文件摘要';
comment on column sys_file_reconcile_run.lock_name is '运行锁名称';
comment on column sys_file_reconcile_run.scanned_file_count is '扫描文件记录数';
comment on column sys_file_reconcile_run.scanned_storage_count is '扫描物理文件数';
comment on column sys_file_reconcile_run.issue_count is '发现异常数';
comment on column sys_file_reconcile_run.new_issue_count is '新增或重新出现异常数';
comment on column sys_file_reconcile_run.resolved_issue_count is '自动恢复异常数';
comment on column sys_file_reconcile_run.started_by is '发起人';
comment on column sys_file_reconcile_run.started_time is '开始时间';
comment on column sys_file_reconcile_run.finished_time is '完成时间';
comment on column sys_file_reconcile_run.error_message is '失败原因';

-- ----------------------------
-- 30、文件存储对账异常表
-- ----------------------------
drop table if exists sys_file_reconcile_issue;
create table sys_file_reconcile_issue (
    issue_id bigserial not null,
    issue_key varchar(64) not null,
    last_run_id varchar(36) not null,
    issue_type varchar(32) not null,
    severity varchar(10) not null,
    file_id varchar(36),
    storage_type varchar(20),
    access_type varchar(20),
    expected_root varchar(20),
    expected_key varchar(500),
    actual_root varchar(20),
    actual_key varchar(500),
    expected_size bigint,
    actual_size bigint,
    expected_hash varchar(64),
    actual_hash varchar(64),
    status varchar(20) not null default 'open',
    detail text,
    occurrence_count integer not null default 1,
    first_seen_time timestamp(3) with time zone not null,
    last_seen_time timestamp(3) with time zone not null,
    handle_action varchar(32),
    handle_reason varchar(500),
    handled_by varchar(64),
    handled_time timestamp(3) with time zone,
    quarantine_key varchar(500),
    primary key (issue_id)
);
create unique index uk_sys_file_reconcile_issue_key on sys_file_reconcile_issue(issue_key);
create index idx_sys_file_reconcile_issue_status_severity on sys_file_reconcile_issue(status, severity);
create index idx_sys_file_reconcile_issue_file on sys_file_reconcile_issue(file_id);
create index idx_sys_file_reconcile_issue_run on sys_file_reconcile_issue(last_run_id);
comment on table sys_file_reconcile_issue is '文件存储对账异常表';
comment on column sys_file_reconcile_issue.issue_id is '异常ID';
comment on column sys_file_reconcile_issue.issue_key is '异常唯一标识';
comment on column sys_file_reconcile_issue.last_run_id is '最近发现任务ID';
comment on column sys_file_reconcile_issue.issue_type is '异常类型';
comment on column sys_file_reconcile_issue.severity is '严重级别';
comment on column sys_file_reconcile_issue.file_id is '文件ID';
comment on column sys_file_reconcile_issue.storage_type is '存储类型';
comment on column sys_file_reconcile_issue.access_type is '访问类型';
comment on column sys_file_reconcile_issue.expected_root is '预期存储区域';
comment on column sys_file_reconcile_issue.expected_key is '预期相对路径';
comment on column sys_file_reconcile_issue.actual_root is '实际存储区域';
comment on column sys_file_reconcile_issue.actual_key is '实际相对路径';
comment on column sys_file_reconcile_issue.expected_size is '预期文件大小';
comment on column sys_file_reconcile_issue.actual_size is '实际文件大小';
comment on column sys_file_reconcile_issue.expected_hash is '预期SHA-256';
comment on column sys_file_reconcile_issue.actual_hash is '实际SHA-256';
comment on column sys_file_reconcile_issue.status is '处理状态';
comment on column sys_file_reconcile_issue.detail is '异常说明';
comment on column sys_file_reconcile_issue.occurrence_count is '发现次数';
comment on column sys_file_reconcile_issue.first_seen_time is '首次发现时间';
comment on column sys_file_reconcile_issue.last_seen_time is '最近发现时间';
comment on column sys_file_reconcile_issue.handle_action is '处理动作';
comment on column sys_file_reconcile_issue.handle_reason is '处理原因';
comment on column sys_file_reconcile_issue.handled_by is '处理人';
comment on column sys_file_reconcile_issue.handled_time is '处理时间';
comment on column sys_file_reconcile_issue.quarantine_key is '隔离区相对路径';

-- ----------------------------
-- 31、插件信息表
-- ----------------------------
drop table if exists sys_plugin;
create table sys_plugin (
  plugin_id          varchar(64)    not null,
  plugin_name        varchar(128)   not null,
  version            varchar(32)    not null,
  installed_version  varchar(32)    default null,
  enabled            char(1)        not null default '0',
  status             varchar(32)    not null default 'discovered',
  source             varchar(32)    not null default 'local',
  backend_path       varchar(255)   default null,
  frontend_path      varchar(255)   default null,
  last_error         varchar(1000)  default null,
  description        varchar(500)   default null,
  create_by          varchar(64)    default '',
  create_time        timestamp(3) with time zone,
  update_by          varchar(64)    default '',
  update_time        timestamp(3) with time zone,
  remark             varchar(500)   default null,
  primary key (plugin_id),
  constraint ck_sys_plugin_enabled check (enabled in ('0', '1')),
  constraint ck_sys_plugin_status check (status in ('discovered', 'installed', 'pending_upgrade', 'error'))
);
comment on table sys_plugin is '插件信息表';
comment on column sys_plugin.plugin_id is '插件ID';
comment on column sys_plugin.plugin_name is '插件名称';
comment on column sys_plugin.version is '当前源码版本';
comment on column sys_plugin.installed_version is '已安装版本';
comment on column sys_plugin.enabled is '是否启用（0启用 1停用）';
comment on column sys_plugin.status is '插件状态';
comment on column sys_plugin.source is '插件来源';
comment on column sys_plugin.backend_path is '后端插件相对路径';
comment on column sys_plugin.frontend_path is '前端插件相对路径';
comment on column sys_plugin.last_error is '最近一次错误信息';
comment on column sys_plugin.description is '插件说明';
comment on column sys_plugin.create_by is '创建者';
comment on column sys_plugin.create_time is '创建时间';
comment on column sys_plugin.update_by is '更新者';
comment on column sys_plugin.update_time is '更新时间';
comment on column sys_plugin.remark is '备注';

-- ----------------------------
-- 32、插件和菜单关联表
-- ----------------------------
drop table if exists sys_plugin_menu;
create table sys_plugin_menu (
  plugin_id          varchar(64)    not null,
  menu_id            bigint         not null,
  menu_key           varchar(255)   not null,
  create_time        timestamp(3) with time zone,
  primary key (plugin_id, menu_id),
  constraint uk_sys_plugin_menu_key unique (plugin_id, menu_key)
);
comment on table sys_plugin_menu is '插件和菜单关联表';
comment on column sys_plugin_menu.plugin_id is '插件ID';
comment on column sys_plugin_menu.menu_id is '菜单ID';
comment on column sys_plugin_menu.menu_key is '插件内菜单自然键';
comment on column sys_plugin_menu.create_time is '创建时间';

-- ----------------------------
-- 33、插件 migration 执行历史表
-- ----------------------------
drop table if exists sys_plugin_migration;
create table sys_plugin_migration (
  plugin_id           varchar(64)   not null,
  migration_path      varchar(255)  not null,
  migration_checksum  varchar(64)   not null,
  version             varchar(32)   default null,
  statement_count     int4          not null default 0,
  status              varchar(32)   not null default 'success',
  error_message       text,
  attempt_count       int4          not null default 0,
  started_time        timestamp(3) with time zone,
  finished_time       timestamp(3) with time zone,
  create_time         timestamp(3) with time zone,
  update_time         timestamp(3) with time zone,
  primary key (plugin_id, migration_path)
);
comment on table sys_plugin_migration is '插件 migration 执行历史表';
comment on column sys_plugin_migration.plugin_id is '插件ID';
comment on column sys_plugin_migration.migration_path is 'migration 相对路径';
comment on column sys_plugin_migration.migration_checksum is 'migration 内容校验值';
comment on column sys_plugin_migration.version is '执行时插件版本';
comment on column sys_plugin_migration.statement_count is 'SQL 语句数量';
comment on column sys_plugin_migration.status is '执行状态';
comment on column sys_plugin_migration.error_message is '失败错误信息';
comment on column sys_plugin_migration.attempt_count is '尝试次数';
comment on column sys_plugin_migration.started_time is '最近开始时间';
comment on column sys_plugin_migration.finished_time is '最近结束时间';
comment on column sys_plugin_migration.create_time is '执行时间';
comment on column sys_plugin_migration.update_time is '更新时间';

-- ----------------------------
-- 34、插件配置表
-- ----------------------------
drop table if exists sys_plugin_config;
create table sys_plugin_config (
  plugin_id          varchar(64)   not null,
  config_key         varchar(128)  not null,
  config_label       varchar(128)  default null,
  config_type        varchar(32)   not null default 'string',
  config_value       text,
  default_value      text,
  required           char(1)       not null default '1',
  secret             char(1)       not null default '1',
  options            text,
  description        varchar(500)  default null,
  create_time        timestamp(3) with time zone,
  update_time        timestamp(3) with time zone,
  primary key (plugin_id, config_key)
);
comment on table sys_plugin_config is '插件配置表';
comment on column sys_plugin_config.plugin_id is '插件ID';
comment on column sys_plugin_config.config_key is '配置键名';
comment on column sys_plugin_config.config_label is '配置展示名称';
comment on column sys_plugin_config.config_type is '配置值类型';
comment on column sys_plugin_config.config_value is '配置值';
comment on column sys_plugin_config.default_value is '默认配置值';
comment on column sys_plugin_config.required is '是否必填（0是 1否）';
comment on column sys_plugin_config.secret is '是否敏感（0是 1否）';
comment on column sys_plugin_config.options is '配置选项JSON';
comment on column sys_plugin_config.description is '配置说明';
comment on column sys_plugin_config.create_time is '创建时间';
comment on column sys_plugin_config.update_time is '更新时间';

-- ----------------------------
-- 35、插件批量操作审计日志表
-- ----------------------------
drop table if exists sys_plugin_operation_log;
create table sys_plugin_operation_log (
  operation_id       bigserial      not null,
  operation          varchar(32)    not null,
  plugin_ids         text,
  dry_run            char(1)        not null default '1',
  continue_on_error  char(1)        not null default '1',
  status             varchar(32)    not null,
  summary            text,
  result             text,
  create_time        timestamp(3) with time zone,
  remark             varchar(500)   default null,
  primary key (operation_id)
);
comment on table sys_plugin_operation_log is '插件批量操作审计日志表';
comment on column sys_plugin_operation_log.operation_id is '操作日志ID';
comment on column sys_plugin_operation_log.operation is '操作类型';
comment on column sys_plugin_operation_log.plugin_ids is '目标插件ID JSON';
comment on column sys_plugin_operation_log.dry_run is '是否预演（0是 1否）';
comment on column sys_plugin_operation_log.continue_on_error is '失败后是否继续（0是 1否）';
comment on column sys_plugin_operation_log.status is '执行状态';
comment on column sys_plugin_operation_log.summary is '执行汇总JSON';
comment on column sys_plugin_operation_log.result is '完整执行结果JSON';
comment on column sys_plugin_operation_log.create_time is '创建时间';
comment on column sys_plugin_operation_log.remark is '备注';

-- ----------------------------
-- 36、插件已验证制品表
-- ----------------------------
create table if not exists sys_plugin_artifact (
  digest             varchar(64)    not null,
  plugin_id          varchar(64)    not null,
  version            varchar(32)    not null,
  key_id             varchar(128)   not null,
  relative_path      varchar(512)   not null,
  manifest_json      text           not null,
  created_by         varchar(64)    default null,
  create_time        timestamp(3) with time zone,
  primary key (digest)
);
create index if not exists idx_sys_plugin_artifact_plugin on sys_plugin_artifact (plugin_id, version);
comment on table sys_plugin_artifact is '插件已验证制品表';
comment on column sys_plugin_artifact.digest is '制品SHA256';
comment on column sys_plugin_artifact.plugin_id is '插件ID';
comment on column sys_plugin_artifact.version is '制品版本';
comment on column sys_plugin_artifact.key_id is '签名公钥标识';
comment on column sys_plugin_artifact.relative_path is '制品存储内不可变相对目录';
comment on column sys_plugin_artifact.manifest_json is '验证后的清单JSON';
comment on column sys_plugin_artifact.created_by is '导入者';
comment on column sys_plugin_artifact.create_time is '创建时间';

-- ----------------------------
-- 37、插件目标发布表
-- ----------------------------
create table if not exists sys_plugin_release (
  plugin_id          varchar(64)    not null,
  target_digest      varchar(64)    default null,
  previous_digest    varchar(64)    default null,
  prepared_digest    varchar(64)    default null,
  generation         varchar(32)    not null,
  expected_workers   integer        not null default 1,
  prepare_status     varchar(16)    not null default 'idle',
  prepared_version   varchar(32)    default null,
  last_error         text           default null,
  create_by          varchar(64)    default null,
  update_by          varchar(64)    default null,
  create_time        timestamp(3) with time zone,
  update_time        timestamp(3) with time zone,
  primary key (plugin_id),
  constraint ck_sys_plugin_release_workers check (expected_workers >= 1),
  constraint ck_sys_plugin_release_prepare check (prepare_status in ('idle', 'preparing', 'prepared', 'failed'))
);
comment on table sys_plugin_release is '插件目标发布表';
comment on column sys_plugin_release.plugin_id is '插件ID';
comment on column sys_plugin_release.target_digest is '目标制品SHA256';
comment on column sys_plugin_release.previous_digest is '上一次目标制品SHA256';
comment on column sys_plugin_release.prepared_digest is '维护准备成功的制品SHA256';
comment on column sys_plugin_release.generation is '目标发布代际UUID';
comment on column sys_plugin_release.expected_workers is '预期宿主worker数量';
comment on column sys_plugin_release.prepare_status is '维护准备状态';
comment on column sys_plugin_release.prepared_version is '维护确认的数据结构安装版本';
comment on column sys_plugin_release.last_error is '维护准备错误';
comment on column sys_plugin_release.create_by is '创建者';
comment on column sys_plugin_release.update_by is '更新者';
comment on column sys_plugin_release.create_time is '创建时间';
comment on column sys_plugin_release.update_time is '更新时间';

-- ----------------------------
-- 38、插件worker加载状态表
-- ----------------------------
create table if not exists sys_plugin_worker (
  worker_id          varchar(32)    not null,
  plugin_id          varchar(64)    not null,
  artifact_digest    varchar(64)    default null,
  version            varchar(32)    default null,
  generation         varchar(32)    default null,
  state              varchar(16)    not null,
  heartbeat_time     timestamp(3) with time zone not null,
  error              text           default null,
  create_time        timestamp(3) with time zone,
  update_time        timestamp(3) with time zone,
  primary key (worker_id, plugin_id),
  constraint ck_sys_plugin_worker_state check (state in ('starting', 'ready', 'failed', 'stopped'))
);
create index if not exists idx_sys_plugin_worker_plugin on sys_plugin_worker (plugin_id, heartbeat_time);
comment on table sys_plugin_worker is '插件worker加载状态表';
comment on column sys_plugin_worker.worker_id is '宿主进程UUID';
comment on column sys_plugin_worker.plugin_id is '插件ID或__runtime__';
comment on column sys_plugin_worker.artifact_digest is '实际加载的制品SHA256';
comment on column sys_plugin_worker.version is '实际加载的制品版本';
comment on column sys_plugin_worker.generation is '实际加载的发布代际UUID';
comment on column sys_plugin_worker.state is 'worker状态';
comment on column sys_plugin_worker.heartbeat_time is 'UTC心跳时间';
comment on column sys_plugin_worker.error is '加载或运行错误';
comment on column sys_plugin_worker.create_time is '创建时间';
comment on column sys_plugin_worker.update_time is '更新时间';

-- ----------------------------
-- 统一认证中心相关表清理
-- ----------------------------
drop table if exists sys_oauth_audit_archive;
drop table if exists sys_oauth_audit_log;
drop table if exists sys_oidc_signing_key;
drop table if exists sys_oauth_refresh_token;
drop table if exists sys_sso_session_client;
drop table if exists sys_sso_session;
drop table if exists sys_oauth_access_policy;
drop table if exists sys_oauth_grant;
drop table if exists sys_oauth_client_resource;
drop table if exists sys_oauth_client_scope;
drop table if exists sys_oauth_scope;
drop table if exists sys_oauth_resource;
drop table if exists sys_oauth_client_uri;
drop table if exists sys_oauth_client_secret;
drop table if exists sys_oauth_client;
drop table if exists sys_identity_subject;

-- ----------------------------
-- 39、统一认证主体关联表
-- ----------------------------
create table sys_identity_subject (
  identity_id   bigserial    not null,
  user_id       bigint       not null,
  subject_id    varchar(36)  not null,
  auth_version  bigint       not null default 1,
  create_by     varchar(64)  default null,
  create_time   timestamp(3) with time zone  not null,
  update_by     varchar(64)  default null,
  update_time   timestamp(3) with time zone  default null,
  primary key (identity_id),
  constraint uk_identity_subject_user unique (user_id),
  constraint uk_identity_subject_subject unique (subject_id),
  constraint fk_identity_subject_user foreign key (user_id) references sys_user (user_id) on delete restrict
);
create index idx_identity_subject_auth_version on sys_identity_subject (auth_version);
comment on table sys_identity_subject is '统一认证主体关联表';
comment on column sys_identity_subject.identity_id is '内部主键';
comment on column sys_identity_subject.user_id is '本地用户ID';
comment on column sys_identity_subject.subject_id is 'OIDC Subject';
comment on column sys_identity_subject.auth_version is '认证安全版本';
comment on column sys_identity_subject.create_by is '创建者';
comment on column sys_identity_subject.create_time is '创建时间';
comment on column sys_identity_subject.update_by is '更新者';
comment on column sys_identity_subject.update_time is '更新时间';

-- ----------------------------
-- 初始化-统一认证主体关联表数据
-- ----------------------------
with seeded_users as materialized (
  select user_id,
         overlay(
           overlay(md5(user_id::text || ':' || clock_timestamp()::text || ':' || random()::text)
             placing '4' from 13 for 1)
           placing '8' from 17 for 1
         ) as uuid_seed
  from sys_user
)
insert into sys_identity_subject (user_id, subject_id, auth_version, create_by, create_time)
select user_id,
       substr(uuid_seed, 1, 8) || '-' || substr(uuid_seed, 9, 4) || '-' ||
       substr(uuid_seed, 13, 4) || '-' || substr(uuid_seed, 17, 4) || '-' ||
       substr(uuid_seed, 21, 12),
       1,
       'initial-sql',
       current_timestamp
from seeded_users;

-- ----------------------------
-- 40、OAuth客户端表
-- ----------------------------
create table sys_oauth_client (
  client_pk                            bigserial     not null,
  client_id                            varchar(64)   not null,
  client_name                          varchar(100)  not null,
  client_type                          varchar(20)   not null,
  token_endpoint_auth_method           varchar(32)   not null,
  grant_types                          jsonb         not null,
  response_types                       jsonb         not null,
  subject_type                         varchar(16)   not null default 'public',
  require_pkce                         smallint      not null default 1,
  require_consent                      smallint      not null default 1,
  trusted_client                       smallint      not null default 0,
  policy_version                       bigint        not null default 1,
  id_token_signed_response_alg         varchar(16)   not null default 'RS256',
  access_token_ttl_seconds             int4          default null,
  refresh_token_idle_seconds           int4          default null,
  refresh_token_absolute_seconds       int4          default null,
  logo_uri                             varchar(500)  default null,
  policy_uri                           varchar(500)  default null,
  tos_uri                              varchar(500)  default null,
  backchannel_logout_session_required  smallint      not null default 1,
  status                               char(1)       not null default '0',
  create_by                            varchar(64)   not null default '',
  create_time                          timestamp(3) with time zone   not null,
  update_by                            varchar(64)   not null default '',
  update_time                          timestamp(3) with time zone   not null,
  remark                               varchar(500)  default null,
  primary key (client_pk),
  constraint uk_oauth_client_client_id unique (client_id)
);
create index idx_oauth_client_status on sys_oauth_client (status);
comment on table sys_oauth_client is 'OAuth客户端表';
comment on column sys_oauth_client.client_pk is '内部主键';
comment on column sys_oauth_client.client_id is 'Client ID';
comment on column sys_oauth_client.client_name is '客户端名称';
comment on column sys_oauth_client.client_type is 'Client 类型';
comment on column sys_oauth_client.token_endpoint_auth_method is 'Token 端点认证方式';
comment on column sys_oauth_client.grant_types is 'Grant Type 列表';
comment on column sys_oauth_client.response_types is 'Response Type 列表';
comment on column sys_oauth_client.subject_type is 'Subject 类型';
comment on column sys_oauth_client.require_pkce is '是否要求 PKCE';
comment on column sys_oauth_client.require_consent is '是否要求同意';
comment on column sys_oauth_client.trusted_client is '是否受信任 Client';
comment on column sys_oauth_client.policy_version is '安全策略版本';
comment on column sys_oauth_client.id_token_signed_response_alg is 'ID Token 算法';
comment on column sys_oauth_client.access_token_ttl_seconds is 'Access Token 有效期';
comment on column sys_oauth_client.refresh_token_idle_seconds is 'Refresh Token 闲置有效期';
comment on column sys_oauth_client.refresh_token_absolute_seconds is 'Refresh Token 绝对有效期';
comment on column sys_oauth_client.logo_uri is 'Logo URI';
comment on column sys_oauth_client.policy_uri is '隐私政策 URI';
comment on column sys_oauth_client.tos_uri is '服务条款 URI';
comment on column sys_oauth_client.backchannel_logout_session_required is '是否要求 Back-Channel Session';
comment on column sys_oauth_client.status is '状态（0正常 1停用）';
comment on column sys_oauth_client.create_by is '创建者';
comment on column sys_oauth_client.create_time is '创建时间';
comment on column sys_oauth_client.update_by is '更新者';
comment on column sys_oauth_client.update_time is '更新时间';
comment on column sys_oauth_client.remark is '备注';

-- ----------------------------
-- 41、OAuth客户端密钥表
-- ----------------------------
create table sys_oauth_client_secret (
  secret_id     varchar(36)   not null,
  client_pk     bigint        not null,
  secret_hash   varchar(100)  not null,
  secret_hint   varchar(12)   not null,
  status        varchar(16)   not null default 'active',
  not_before    timestamp(3) with time zone   not null,
  expires_at    timestamp(3) with time zone   default null,
  last_used_at  timestamp(3) with time zone   default null,
  create_by     varchar(64)   not null,
  create_time   timestamp(3) with time zone   not null,
  revoked_by    varchar(64)   default null,
  revoked_at    timestamp(3) with time zone   default null,
  primary key (secret_id),
  constraint fk_oauth_client_secret_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict
);
create index idx_oauth_client_secret_client on sys_oauth_client_secret (client_pk, status);
comment on table sys_oauth_client_secret is 'OAuth客户端密钥表';
comment on column sys_oauth_client_secret.secret_id is 'Secret ID';
comment on column sys_oauth_client_secret.client_pk is 'Client 主键';
comment on column sys_oauth_client_secret.secret_hash is 'Secret 强哈希';
comment on column sys_oauth_client_secret.secret_hint is 'Secret 提示';
comment on column sys_oauth_client_secret.status is 'Secret 状态';
comment on column sys_oauth_client_secret.not_before is '生效时间';
comment on column sys_oauth_client_secret.expires_at is '过期时间';
comment on column sys_oauth_client_secret.last_used_at is '最近使用时间';
comment on column sys_oauth_client_secret.create_by is '创建者';
comment on column sys_oauth_client_secret.create_time is '创建时间';
comment on column sys_oauth_client_secret.revoked_by is '撤销者';
comment on column sys_oauth_client_secret.revoked_at is '撤销时间';

-- ----------------------------
-- 42、OAuth客户端URI表
-- ----------------------------
create table sys_oauth_client_uri (
  uri_id       bigserial      not null,
  client_pk    bigint         not null,
  uri_type     varchar(32)    not null,
  uri          varchar(1000)  not null,
  uri_hash     char(64)       not null,
  is_default   smallint       not null default 0,
  status       char(1)        not null default '0',
  create_time  timestamp(3) with time zone    not null,
  primary key (uri_id),
  constraint uk_oauth_client_uri_hash unique (client_pk, uri_type, uri_hash),
  constraint fk_oauth_client_uri_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict
);
create index idx_oauth_client_uri_type on sys_oauth_client_uri (client_pk, uri_type, status);
comment on table sys_oauth_client_uri is 'OAuth客户端URI表';
comment on column sys_oauth_client_uri.uri_id is 'URI 主键';
comment on column sys_oauth_client_uri.client_pk is 'Client 主键';
comment on column sys_oauth_client_uri.uri_type is 'URI 类型';
comment on column sys_oauth_client_uri.uri is '精确 URI';
comment on column sys_oauth_client_uri.uri_hash is 'URI SHA-256 摘要';
comment on column sys_oauth_client_uri.is_default is '是否默认 URI';
comment on column sys_oauth_client_uri.status is '状态（0正常 1停用）';
comment on column sys_oauth_client_uri.create_time is '创建时间';

-- ----------------------------
-- 43、OAuth资源服务器表
-- ----------------------------
create table sys_oauth_resource (
  resource_pk               bigserial     not null,
  resource_id               varchar(64)   not null,
  resource_name             varchar(100)  not null,
  audience                  varchar(500)  not null,
  token_format              varchar(16)   not null default 'jwt',
  signing_alg               varchar(16)   not null default 'RS256',
  access_token_ttl_seconds  int4          default null,
  introspection_client_pk   bigint        default null,
  allowed_claims            jsonb         not null,
  status                    char(1)       not null default '0',
  create_by                 varchar(64)   not null,
  create_time               timestamp(3) with time zone   not null,
  update_by                 varchar(64)   not null,
  update_time               timestamp(3) with time zone   not null,
  remark                    varchar(500)  default null,
  primary key (resource_pk),
  constraint uk_oauth_resource_resource_id unique (resource_id),
  constraint uk_oauth_resource_audience unique (audience),
  constraint fk_oauth_resource_introspection_client foreign key (introspection_client_pk) references sys_oauth_client (client_pk) on delete restrict
);
create index idx_oauth_resource_status on sys_oauth_resource (status);
comment on table sys_oauth_resource is 'OAuth资源服务器表';
comment on column sys_oauth_resource.resource_pk is '内部主键';
comment on column sys_oauth_resource.resource_id is 'Resource ID';
comment on column sys_oauth_resource.resource_name is 'Resource 名称';
comment on column sys_oauth_resource.audience is 'Access Token audience';
comment on column sys_oauth_resource.token_format is 'Token 格式';
comment on column sys_oauth_resource.signing_alg is '签名算法';
comment on column sys_oauth_resource.access_token_ttl_seconds is 'Access Token 有效期';
comment on column sys_oauth_resource.introspection_client_pk is 'Introspection Client 主键';
comment on column sys_oauth_resource.allowed_claims is '允许的 Claims';
comment on column sys_oauth_resource.status is '状态（0正常 1停用）';
comment on column sys_oauth_resource.create_by is '创建者';
comment on column sys_oauth_resource.create_time is '创建时间';
comment on column sys_oauth_resource.update_by is '更新者';
comment on column sys_oauth_resource.update_time is '更新时间';
comment on column sys_oauth_resource.remark is '备注';

-- ----------------------------
-- 44、OAuth权限范围表
-- ----------------------------
create table sys_oauth_scope (
  scope_pk          bigserial     not null,
  scope_code        varchar(100)  not null,
  scope_name        varchar(100)  not null,
  scope_type        varchar(16)   not null,
  resource_pk       bigint        default null,
  claims            jsonb         not null,
  consent_required  smallint      not null default 1,
  sensitive         smallint      not null default 0,
  status            char(1)       not null default '0',
  create_by         varchar(64)   not null,
  create_time       timestamp(3) with time zone   not null,
  update_by         varchar(64)   not null,
  update_time       timestamp(3) with time zone   not null,
  remark            varchar(500)  default null,
  primary key (scope_pk),
  constraint uk_oauth_scope_code unique (scope_code),
  constraint fk_oauth_scope_resource foreign key (resource_pk) references sys_oauth_resource (resource_pk) on delete restrict
);
create index idx_oauth_scope_status on sys_oauth_scope (status);
create index idx_oauth_scope_resource on sys_oauth_scope (resource_pk);
alter sequence sys_oauth_scope_scope_pk_seq restart 8;
comment on table sys_oauth_scope is 'OAuth权限范围表';
comment on column sys_oauth_scope.scope_pk is '内部主键';
comment on column sys_oauth_scope.scope_code is 'Scope 编码';
comment on column sys_oauth_scope.scope_name is 'Scope 名称';
comment on column sys_oauth_scope.scope_type is 'Scope 类型';
comment on column sys_oauth_scope.resource_pk is 'Resource 主键';
comment on column sys_oauth_scope.claims is 'Claims 列表';
comment on column sys_oauth_scope.consent_required is '是否需要同意';
comment on column sys_oauth_scope.sensitive is '是否敏感';
comment on column sys_oauth_scope.status is '状态（0正常 1停用）';
comment on column sys_oauth_scope.create_by is '创建者';
comment on column sys_oauth_scope.create_time is '创建时间';
comment on column sys_oauth_scope.update_by is '更新者';
comment on column sys_oauth_scope.update_time is '更新时间';
comment on column sys_oauth_scope.remark is '备注';

-- ----------------------------
-- 初始化-OAuth权限范围表数据
-- ----------------------------
insert into sys_oauth_scope values(1, 'openid', 'OpenID', 'identity', null, '["sub"]'::jsonb, 1, 0, '0', 'system', current_timestamp, 'system', current_timestamp, 'OIDC 必需身份范围');
insert into sys_oauth_scope values(2, 'profile', '基础资料', 'identity', null, '["name", "preferred_username", "picture", "updated_at"]'::jsonb, 1, 0, '0', 'system', current_timestamp, 'system', current_timestamp, 'OIDC Profile');
insert into sys_oauth_scope values(3, 'email', '邮箱', 'identity', null, '["email", "email_verified"]'::jsonb, 1, 1, '0', 'system', current_timestamp, 'system', current_timestamp, 'OIDC Email');
insert into sys_oauth_scope values(4, 'phone', '手机号', 'identity', null, '["phone_number", "phone_number_verified"]'::jsonb, 1, 1, '0', 'system', current_timestamp, 'system', current_timestamp, 'OIDC Phone');
insert into sys_oauth_scope values(5, 'roles', '角色', 'identity', null, '["roles"]'::jsonb, 1, 1, '0', 'system', current_timestamp, 'system', current_timestamp, '外部角色 Claim');
insert into sys_oauth_scope values(6, 'dept', '部门', 'identity', null, '["dept_id", "dept_name"]'::jsonb, 1, 1, '0', 'system', current_timestamp, 'system', current_timestamp, '外部部门 Claim');
insert into sys_oauth_scope values(7, 'offline_access', '离线访问', 'identity', null, '[]'::jsonb, 1, 1, '0', 'system', current_timestamp, 'system', current_timestamp, '允许签发 Refresh Token');

-- ----------------------------
-- 45、OAuth客户端和权限范围关联表
-- ----------------------------
create table sys_oauth_client_scope (
  client_pk       bigint       not null,
  scope_pk        bigint       not null,
  is_default      smallint     not null default 0,
  pre_authorized  smallint     not null default 0,
  claim_filter    jsonb        default null,
  create_time     timestamp(3) with time zone  not null,
  primary key (client_pk, scope_pk),
  constraint fk_oauth_client_scope_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict,
  constraint fk_oauth_client_scope_scope foreign key (scope_pk) references sys_oauth_scope (scope_pk) on delete restrict
);
create index idx_oauth_client_scope_scope on sys_oauth_client_scope (scope_pk);
comment on table sys_oauth_client_scope is 'OAuth客户端和权限范围关联表';
comment on column sys_oauth_client_scope.client_pk is 'Client 主键';
comment on column sys_oauth_client_scope.scope_pk is 'Scope 主键';
comment on column sys_oauth_client_scope.is_default is '是否默认 Scope';
comment on column sys_oauth_client_scope.pre_authorized is '是否预授权';
comment on column sys_oauth_client_scope.claim_filter is 'Client Claim 过滤策略';
comment on column sys_oauth_client_scope.create_time is '创建时间';

-- ----------------------------
-- 46、OAuth客户端和资源服务器关联表
-- ----------------------------
create table sys_oauth_client_resource (
  client_pk    bigint       not null,
  resource_pk  bigint       not null,
  is_default   smallint     not null default 0,
  create_time  timestamp(3) with time zone  not null,
  primary key (client_pk, resource_pk),
  constraint fk_oauth_client_resource_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict,
  constraint fk_oauth_client_resource_resource foreign key (resource_pk) references sys_oauth_resource (resource_pk) on delete restrict
);
create index idx_oauth_client_resource_resource on sys_oauth_client_resource (resource_pk);
comment on table sys_oauth_client_resource is 'OAuth客户端和资源服务器关联表';
comment on column sys_oauth_client_resource.client_pk is 'Client 主键';
comment on column sys_oauth_client_resource.resource_pk is 'Resource 主键';
comment on column sys_oauth_client_resource.is_default is '是否默认 Resource';
comment on column sys_oauth_client_resource.create_time is '创建时间';

-- ----------------------------
-- 47、用户应用访问控制表
-- ----------------------------
create table sys_oauth_access_policy (
  user_id       bigint        not null,
  client_pk     bigint        not null,
  access_status varchar(16)   not null default 'allowed',
  reason        varchar(200),
  update_by     varchar(64)   not null,
  update_time   timestamp(3) with time zone not null,
  primary key (user_id, client_pk),
  constraint fk_oauth_access_user foreign key (user_id) references sys_user (user_id) on delete restrict,
  constraint fk_oauth_access_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict
);
comment on table sys_oauth_access_policy is 'OAuth用户应用访问控制表';
comment on column sys_oauth_access_policy.user_id is '用户ID';
comment on column sys_oauth_access_policy.client_pk is 'Client 主键';
comment on column sys_oauth_access_policy.access_status is 'allowed允许 blocked禁止';
comment on column sys_oauth_access_policy.reason is '访问控制原因';
comment on column sys_oauth_access_policy.update_by is '操作人';
comment on column sys_oauth_access_policy.update_time is '操作时间';

-- ----------------------------
-- 48、OAuth授权记录表
-- ----------------------------
create table sys_oauth_grant (
  grant_id               varchar(36)   not null,
  user_id                bigint        not null,
  subject_id             varchar(36)   not null,
  client_pk              bigint        not null,
  granted_scopes         jsonb         not null,
  granted_resources      jsonb         not null,
  remembered_scopes      jsonb         default null,
  remembered_resources   jsonb         default null,
  client_policy_version  bigint        not null,
  status                 varchar(16)   not null default 'active',
  consented_at           timestamp(3) with time zone   not null,
  expires_at             timestamp(3) with time zone   default null,
  revoked_at             timestamp(3) with time zone   default null,
  revoke_reason          varchar(200)  default null,
  last_used_at           timestamp(3) with time zone   default null,
  primary key (grant_id),
  constraint fk_oauth_grant_user foreign key (user_id) references sys_user (user_id) on delete restrict,
  constraint fk_oauth_grant_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict
);
create index idx_oauth_grant_user on sys_oauth_grant (user_id, status);
create index idx_oauth_grant_client on sys_oauth_grant (client_pk, status);
create index idx_oauth_grant_user_client on sys_oauth_grant (user_id, client_pk, status);
comment on table sys_oauth_grant is 'OAuth授权记录表';
comment on column sys_oauth_grant.grant_id is 'Grant ID';
comment on column sys_oauth_grant.user_id is '用户ID';
comment on column sys_oauth_grant.subject_id is 'Subject 快照';
comment on column sys_oauth_grant.client_pk is 'Client 主键';
comment on column sys_oauth_grant.granted_scopes is '已同意 Scope';
comment on column sys_oauth_grant.granted_resources is '已同意 Resource audience';
comment on column sys_oauth_grant.client_policy_version is 'Client Policy Version';
comment on column sys_oauth_grant.status is 'Grant 状态';
comment on column sys_oauth_grant.consented_at is '同意时间';
comment on column sys_oauth_grant.expires_at is '过期时间';
comment on column sys_oauth_grant.revoked_at is '撤销时间';
comment on column sys_oauth_grant.revoke_reason is '撤销原因';
comment on column sys_oauth_grant.last_used_at is '最近使用时间';

-- ----------------------------
-- 49、OIDC单点登录会话表
-- ----------------------------
create table sys_sso_session (
  sid                  varchar(36)   not null,
  session_secret_hash  char(64)      not null,
  user_id              bigint        not null,
  subject_id           varchar(36)   not null,
  auth_version         bigint        not null,
  auth_time            timestamp(3) with time zone   not null,
  last_seen_at         timestamp(3) with time zone   not null,
  idle_expires_at      timestamp(3) with time zone   not null,
  absolute_expires_at  timestamp(3) with time zone   not null,
  acr                  varchar(100)  not null,
  amr                  jsonb         not null,
  remember_me          smallint      not null default 0,
  ip_address           varchar(128)  default null,
  user_agent_hash      char(64)      default null,
  status               varchar(16)   not null default 'active',
  revoked_at           timestamp(3) with time zone   default null,
  revoke_reason        varchar(200)  default null,
  create_time          timestamp(3) with time zone   not null,
  primary key (sid),
  constraint fk_sso_session_user foreign key (user_id) references sys_user (user_id) on delete restrict
);
create index idx_sso_session_user on sys_sso_session (user_id, status);
create index idx_sso_session_idle on sys_sso_session (status, idle_expires_at);
create index idx_sso_session_absolute on sys_sso_session (status, absolute_expires_at);
comment on table sys_sso_session is 'OIDC单点登录会话表';
comment on column sys_sso_session.sid is 'OIDC Session ID';
comment on column sys_sso_session.session_secret_hash is 'SSO Cookie 摘要';
comment on column sys_sso_session.user_id is '用户ID';
comment on column sys_sso_session.subject_id is 'Subject 快照';
comment on column sys_sso_session.auth_version is '认证安全版本';
comment on column sys_sso_session.auth_time is '认证时间';
comment on column sys_sso_session.last_seen_at is '最近活动时间';
comment on column sys_sso_session.idle_expires_at is '闲置过期时间';
comment on column sys_sso_session.absolute_expires_at is '绝对过期时间';
comment on column sys_sso_session.acr is '认证上下文';
comment on column sys_sso_session.amr is '认证方式';
comment on column sys_sso_session.remember_me is '是否长期会话';
comment on column sys_sso_session.ip_address is '登录 IP';
comment on column sys_sso_session.user_agent_hash is 'User-Agent 摘要';
comment on column sys_sso_session.status is 'Session 状态';
comment on column sys_sso_session.revoked_at is '撤销时间';
comment on column sys_sso_session.revoke_reason is '撤销原因';
comment on column sys_sso_session.create_time is '创建时间';

-- ----------------------------
-- 50、SSO会话与参与应用关联表
-- ----------------------------
create table sys_sso_session_client (
  sid           varchar(36)                  not null,
  client_pk     bigint                       not null,
  create_time   timestamp(3) with time zone  not null,
  last_used_at  timestamp(3) with time zone  not null,
  primary key (sid, client_pk),
  constraint fk_sso_session_client_sid foreign key (sid) references sys_sso_session (sid) on delete restrict,
  constraint fk_sso_session_client_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict
);
create index idx_sso_session_client_client on sys_sso_session_client (client_pk);
comment on table sys_sso_session_client is 'SSO会话参与应用';
comment on column sys_sso_session_client.sid is 'SSO Session ID';
comment on column sys_sso_session_client.client_pk is 'Client 主键';
comment on column sys_sso_session_client.create_time is '首次授权时间';
comment on column sys_sso_session_client.last_used_at is '最近授权时间';

-- ----------------------------
-- 51、OAuth刷新令牌表
-- ----------------------------
create table sys_oauth_refresh_token (
  token_id              varchar(36)   not null,
  token_hash            char(64)      not null,
  family_id             varchar(36)   not null,
  parent_token_id       varchar(36)   default null,
  replaced_by_token_id  varchar(36)   default null,
  grant_id              varchar(36)   not null,
  user_id               bigint        not null,
  subject_id            varchar(36)   not null,
  auth_version          bigint        not null,
  client_pk             bigint        not null,
  sid                   varchar(36)   not null,
  scopes                jsonb         not null,
  resources             jsonb         not null,
  status                varchar(24)   not null default 'active',
  issued_at             timestamp(3) with time zone   not null,
  last_used_at          timestamp(3) with time zone   default null,
  idle_expires_at       timestamp(3) with time zone   not null,
  absolute_expires_at   timestamp(3) with time zone   not null,
  revoked_at            timestamp(3) with time zone   default null,
  revoke_reason         varchar(200)  default null,
  reuse_detected_at     timestamp(3) with time zone   default null,
  primary key (token_id),
  constraint uk_oauth_refresh_token_hash unique (token_hash),
  constraint fk_oauth_refresh_parent foreign key (parent_token_id) references sys_oauth_refresh_token (token_id) on delete restrict,
  constraint fk_oauth_refresh_replaced_by foreign key (replaced_by_token_id) references sys_oauth_refresh_token (token_id) on delete restrict,
  constraint fk_oauth_refresh_grant foreign key (grant_id) references sys_oauth_grant (grant_id) on delete restrict,
  constraint fk_oauth_refresh_user foreign key (user_id) references sys_user (user_id) on delete restrict,
  constraint fk_oauth_refresh_client foreign key (client_pk) references sys_oauth_client (client_pk) on delete restrict,
  constraint fk_oauth_refresh_sid foreign key (sid) references sys_sso_session (sid) on delete restrict
);
create index idx_oauth_refresh_family on sys_oauth_refresh_token (family_id, status);
create index idx_oauth_refresh_user on sys_oauth_refresh_token (user_id, status);
create index idx_oauth_refresh_client on sys_oauth_refresh_token (client_pk, status);
create index idx_oauth_refresh_sid on sys_oauth_refresh_token (sid, status);
create index idx_oauth_refresh_expire on sys_oauth_refresh_token (status, absolute_expires_at);
comment on table sys_oauth_refresh_token is 'OAuth刷新令牌表';
comment on column sys_oauth_refresh_token.token_id is 'Token ID';
comment on column sys_oauth_refresh_token.token_hash is 'Token HMAC 摘要';
comment on column sys_oauth_refresh_token.family_id is 'Token Family ID';
comment on column sys_oauth_refresh_token.parent_token_id is '父 Token ID';
comment on column sys_oauth_refresh_token.replaced_by_token_id is '替代 Token ID';
comment on column sys_oauth_refresh_token.grant_id is 'Grant ID';
comment on column sys_oauth_refresh_token.user_id is '用户ID';
comment on column sys_oauth_refresh_token.subject_id is 'Subject 快照';
comment on column sys_oauth_refresh_token.auth_version is '认证安全版本';
comment on column sys_oauth_refresh_token.client_pk is 'Client 主键';
comment on column sys_oauth_refresh_token.sid is 'SSO Session ID';
comment on column sys_oauth_refresh_token.scopes is '绑定 Scope';
comment on column sys_oauth_refresh_token.resources is '绑定 Resource audience';
comment on column sys_oauth_refresh_token.status is 'Token 状态';
comment on column sys_oauth_refresh_token.issued_at is '签发时间';
comment on column sys_oauth_refresh_token.last_used_at is '最近使用时间';
comment on column sys_oauth_refresh_token.idle_expires_at is '闲置过期时间';
comment on column sys_oauth_refresh_token.absolute_expires_at is '绝对过期时间';
comment on column sys_oauth_refresh_token.revoked_at is '撤销时间';
comment on column sys_oauth_refresh_token.revoke_reason is '撤销原因';
comment on column sys_oauth_refresh_token.reuse_detected_at is '重放检测时间';

-- ----------------------------
-- 52、OIDC签名密钥表
-- ----------------------------
create table sys_oidc_signing_key (
  key_pk                  bigserial      not null,
  kid                     varchar(100)   not null,
  key_use                 varchar(16)    not null default 'sig',
  alg                     varchar(16)    not null default 'RS256',
  public_jwk              jsonb          not null,
  private_key_ref         varchar(1000)  default null,
  private_key_ciphertext  text           default null,
  status                  varchar(16)    not null,
  publish_at              timestamp(3) with time zone    not null,
  signing_start_at        timestamp(3) with time zone    default null,
  signing_stop_at         timestamp(3) with time zone    default null,
  remove_from_jwks_at     timestamp(3) with time zone    default null,
  create_by               varchar(64)    not null,
  create_time             timestamp(3) with time zone    not null,
  remark                  varchar(500)   default null,
  primary key (key_pk),
  constraint uk_oidc_signing_key_kid unique (kid),
  constraint ck_oidc_signing_key_private_material check (num_nonnulls(private_key_ref, private_key_ciphertext) = 1)
);
create index idx_oidc_signing_key_status_publish on sys_oidc_signing_key (status, publish_at);
create index idx_oidc_signing_key_jwks_remove on sys_oidc_signing_key (status, remove_from_jwks_at);
comment on table sys_oidc_signing_key is 'OIDC签名密钥表';
comment on column sys_oidc_signing_key.key_pk is '内部主键';
comment on column sys_oidc_signing_key.kid is 'JWKS Key ID';
comment on column sys_oidc_signing_key.key_use is 'JWK 用途';
comment on column sys_oidc_signing_key.alg is '签名算法';
comment on column sys_oidc_signing_key.public_jwk is '公开 JWK';
comment on column sys_oidc_signing_key.private_key_ref is 'KMS/HSM/文件引用';
comment on column sys_oidc_signing_key.private_key_ciphertext is '加密私钥材料';
comment on column sys_oidc_signing_key.status is '密钥状态';
comment on column sys_oidc_signing_key.publish_at is '发布时间';
comment on column sys_oidc_signing_key.signing_start_at is '开始签名时间';
comment on column sys_oidc_signing_key.signing_stop_at is '停止签名时间';
comment on column sys_oidc_signing_key.remove_from_jwks_at is '移出 JWKS 时间';
comment on column sys_oidc_signing_key.create_by is '创建者';
comment on column sys_oidc_signing_key.create_time is '创建时间';
comment on column sys_oidc_signing_key.remark is '备注';

-- ----------------------------
-- 53、OAuth审计日志表
-- ----------------------------
create table sys_oauth_audit_log (
  event_id      bigserial     not null,
  trace_id      varchar(64)   default null,
  event_type    varchar(64)   not null,
  result        varchar(16)   not null,
  risk_level    varchar(16)   not null default 'normal',
  client_id     varchar(64)   default null,
  resource_id   varchar(64)   default null,
  user_id       bigint        default null,
  subject_id    varchar(36)   default null,
  sid           varchar(36)   default null,
  grant_id      varchar(36)   default null,
  token_id      varchar(36)   default null,
  ip_address    varchar(128)  default null,
  user_agent    varchar(500)  default null,
  failure_code  varchar(64)   default null,
  detail        jsonb         default null,
  create_time   timestamp(3) with time zone   not null,
  primary key (event_id)
);
create index idx_oauth_audit_time on sys_oauth_audit_log (create_time);
create index idx_oauth_audit_client on sys_oauth_audit_log (client_id, create_time);
create index idx_oauth_audit_user on sys_oauth_audit_log (user_id, create_time);
create index idx_oauth_audit_event on sys_oauth_audit_log (event_type, result, create_time);
create index idx_oauth_audit_risk on sys_oauth_audit_log (risk_level, create_time);
comment on table sys_oauth_audit_log is 'OAuth审计日志表';
comment on column sys_oauth_audit_log.event_id is '事件ID';
comment on column sys_oauth_audit_log.trace_id is '链路追踪ID';
comment on column sys_oauth_audit_log.event_type is '事件类型';
comment on column sys_oauth_audit_log.result is '结果';
comment on column sys_oauth_audit_log.risk_level is '风险等级';
comment on column sys_oauth_audit_log.client_id is 'Client ID 快照';
comment on column sys_oauth_audit_log.resource_id is 'Resource ID 快照';
comment on column sys_oauth_audit_log.user_id is '用户ID快照';
comment on column sys_oauth_audit_log.subject_id is 'Subject 快照';
comment on column sys_oauth_audit_log.sid is 'SSO Session ID';
comment on column sys_oauth_audit_log.grant_id is 'Grant ID';
comment on column sys_oauth_audit_log.token_id is 'Token ID';
comment on column sys_oauth_audit_log.ip_address is '客户端 IP';
comment on column sys_oauth_audit_log.user_agent is '脱敏 User-Agent';
comment on column sys_oauth_audit_log.failure_code is '失败码';
comment on column sys_oauth_audit_log.detail is '脱敏扩展详情';
comment on column sys_oauth_audit_log.create_time is '事件时间';

-- ----------------------------
-- 54、OAuth审计归档表
-- ----------------------------
create table sys_oauth_audit_archive (
  event_id      bigint        not null,
  trace_id      varchar(64)   default null,
  event_type    varchar(64)   not null,
  result        varchar(16)   not null,
  risk_level    varchar(16)   not null,
  client_id     varchar(64)   default null,
  resource_id   varchar(64)   default null,
  user_id       bigint        default null,
  subject_id    varchar(36)   default null,
  sid           varchar(36)   default null,
  grant_id      varchar(36)   default null,
  token_id      varchar(36)   default null,
  ip_address    varchar(128)  default null,
  user_agent    varchar(500)  default null,
  failure_code  varchar(64)   default null,
  detail        jsonb         default null,
  create_time   timestamp(3) with time zone   not null,
  archived_at   timestamp(3) with time zone   not null,
  primary key (event_id)
);
create index idx_oauth_audit_archive_time on sys_oauth_audit_archive (create_time);
create index idx_oauth_audit_archive_event on sys_oauth_audit_archive (event_type, result, create_time);
comment on table sys_oauth_audit_archive is 'OAuth审计归档表';
comment on column sys_oauth_audit_archive.event_id is '原事件ID';
comment on column sys_oauth_audit_archive.trace_id is '链路追踪ID';
comment on column sys_oauth_audit_archive.event_type is '事件类型';
comment on column sys_oauth_audit_archive.result is '结果';
comment on column sys_oauth_audit_archive.risk_level is '风险等级';
comment on column sys_oauth_audit_archive.client_id is 'Client ID 快照';
comment on column sys_oauth_audit_archive.resource_id is 'Resource ID 快照';
comment on column sys_oauth_audit_archive.user_id is '用户ID快照';
comment on column sys_oauth_audit_archive.subject_id is 'Subject 快照';
comment on column sys_oauth_audit_archive.sid is 'SSO Session ID';
comment on column sys_oauth_audit_archive.grant_id is 'Grant ID';
comment on column sys_oauth_audit_archive.token_id is 'Token ID';
comment on column sys_oauth_audit_archive.ip_address is '客户端 IP';
comment on column sys_oauth_audit_archive.user_agent is '脱敏 User-Agent';
comment on column sys_oauth_audit_archive.failure_code is '失败码';
comment on column sys_oauth_audit_archive.detail is '脱敏扩展详情';
comment on column sys_oauth_audit_archive.create_time is '事件时间';
comment on column sys_oauth_audit_archive.archived_at is '归档时间';

CREATE OR REPLACE FUNCTION "find_in_set"(int8, varchar)
    RETURNS "pg_catalog"."bool" AS $BODY$
DECLARE
    STR ALIAS FOR $1;
    STRS ALIAS FOR $2;
    POS INTEGER;
    STATUS BOOLEAN;
BEGIN
    SELECT POSITION( ','||STR||',' IN ','||STRS||',') INTO POS;
    IF POS > 0 THEN
        STATUS = TRUE;
    ELSE
        STATUS = FALSE;
    END IF;
    RETURN STATUS;
END;
$BODY$
    LANGUAGE plpgsql VOLATILE
                     COST 100;

create or replace view list_column as
SELECT c.relname                                                                           AS table_name,
       a.attname                                                                           AS column_name,
       d.description                                                                       AS column_comment,
       CASE
           WHEN a.attnotnull AND con.conname IS NULL THEN '1'
           ELSE '0'
           END                                                                             AS is_required,
       CASE
           WHEN con.conname IS NOT NULL THEN '1'
           ELSE '0'
           END                                                                             AS is_pk,
       a.attnum                                                                            AS sort,
       CASE
           WHEN "position"(pg_get_expr(ad.adbin, ad.adrelid), ((c.relname::text || '_'::text) || a.attname
                           ::text) || '_seq'::text) > 0 THEN '1'
           ELSE '0'
           END                                                                             AS is_increment,
       btrim(
                   CASE
                       WHEN t.typelem <> 0::oid AND t.typlen = '-1'::integer THEN 'ARRAY'::text
            ELSE
            CASE
                WHEN t.typtype = 'd'::"char" THEN format_type(t.typbasetype, t.typtypmod)
                ELSE format_type(a.atttypid, a.atttypmod)
            END
        END, '"'::text) AS column_type
FROM pg_attribute a
         JOIN (pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid) ON a.attrelid = c.oid
         LEFT JOIN pg_description d ON d.objoid = c.oid AND a.attnum = d.objsubid
         LEFT JOIN pg_constraint con ON con.conrelid = c.oid AND (a.attnum = ANY (con.conkey))
         LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
         LEFT JOIN pg_type t ON a.atttypid = t.oid
WHERE (c.relkind = ANY (ARRAY['r'::"char", 'p'::"char"]))
  AND a.attnum > 0
  AND n.nspname = 'public'::name
  AND not a.attisdropped
  ORDER BY c.relname, a.attnum;

create or replace view list_table as
SELECT c.relname              AS table_name,
       obj_description(c.oid) AS table_comment,
       -- PostgreSQL catalogs do not record table creation/update instants.
       NULL::timestamptz      AS create_time,
       NULL::timestamptz      AS update_time
FROM pg_class c
         LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (c.relkind = ANY (ARRAY['r'::"char", 'p'::"char"]))
  AND c.relname !~~ 'spatial_%'::text AND n.nspname = 'public'::name AND n.nspname <> ''::name;

CREATE OR REPLACE FUNCTION substring_index(varchar, varchar, integer)
RETURNS varchar AS $$
DECLARE
tokens varchar[];
length integer ;
indexnum integer;
BEGIN
tokens := pg_catalog.string_to_array($1, $2);
length := pg_catalog.array_upper(tokens, 1);
indexnum := length - ($3 * -1) + 1;
IF $3 >= 0 THEN
RETURN pg_catalog.array_to_string(tokens[1:$3], $2);
ELSE
RETURN pg_catalog.array_to_string(tokens[indexnum:length], $2);
END IF;
END;
$$ IMMUTABLE STRICT LANGUAGE PLPGSQL;
