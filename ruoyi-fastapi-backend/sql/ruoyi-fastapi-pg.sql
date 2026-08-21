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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
    password varchar(100) default '',
    status char(1) default '0',
    del_flag char(1) default '0',
    login_ip varchar(128) default '',
    login_date timestamp(0),
    pwd_update_date timestamp(0),
    create_by varchar(64) default '',
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
insert into sys_user values(1,  103, 'admin',   '超级管理员', '00', 'niangao@163.com', '15888888888', '1', '', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', current_timestamp, current_timestamp, 'admin', current_timestamp, '', null, '管理员');
insert into sys_user values(2,  105, 'niangao', '年糕', 			'00', 'niangao@qq.com',  '15666666666', '1', '', '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', '127.0.0.1', current_timestamp, current_timestamp, 'admin', current_timestamp, '', null, '测试员');

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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
    create_time timestamp(0),
    update_by varchar(64)  default '',
    update_time timestamp(0),
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
insert into sys_menu values(109,  '在线用户', 2,   '1', 'online',              'monitor/online/index',              '', '', 1, 0, 'C', '0', '0', 'monitor:online:list',              'online',        'admin', current_timestamp, '', null, '在线用户菜单');
insert into sys_menu values(110,  '定时任务', 2,   '2', 'job',                 'monitor/job/index',                 '', '', 1, 0, 'C', '0', '0', 'monitor:job:list',                 'job',           'admin', current_timestamp, '', null, '定时任务菜单');
insert into sys_menu values(111,  '数据监控', 2,   '3', 'druid',               'monitor/druid/index',               '', '', 1, 0, 'C', '0', '0', 'monitor:druid:list',               'druid',         'admin', current_timestamp, '', null, '数据监控菜单');
insert into sys_menu values(112,  '服务监控', 2,   '4', 'server',              'monitor/server/index',              '', '', 1, 0, 'C', '0', '0', 'monitor:server:list',              'server',        'admin', current_timestamp, '', null, '服务监控菜单');
insert into sys_menu values(113,  '缓存监控', 2,   '5', 'cache',               'monitor/cache/index',               '', '', 1, 0, 'C', '0', '0', 'monitor:cache:list',               'redis',         'admin', current_timestamp, '', null, '缓存监控菜单');
insert into sys_menu values(114,  '缓存列表', 2,   '6', 'cacheList',           'monitor/cache/list',                '', '', 1, 0, 'C', '0', '0', 'monitor:cache:list',               'redis-list',    'admin', current_timestamp, '', null, '缓存列表菜单');
insert into sys_menu values(118,  '传输加密', 2,   '7', 'transportCrypto',     'monitor/transportCrypto/index',     '', '', 1, 0, 'C', '0', '0', 'monitor:transportCrypto:list',     'chart',         'admin', current_timestamp, '', null, '传输加密监控菜单');
insert into sys_menu values(115,  '表单构建', 3,   '1', 'build',               'tool/build/index',                  '', '', 1, 0, 'C', '0', '0', 'tool:build:list',                  'build',         'admin', current_timestamp, '', null, '表单构建菜单');
insert into sys_menu values(116,  '代码生成', 3,   '2', 'gen',                 'tool/gen/index',                    '', '', 1, 0, 'C', '0', '0', 'tool:gen:list',                    'code',          'admin', current_timestamp, '', null, '代码生成菜单');
insert into sys_menu values(117,  '系统接口', 3,   '3', 'swagger',             'tool/swagger/index',                '', '', 1, 0, 'C', '0', '0', 'tool:swagger:list',                'swagger',       'admin', current_timestamp, '', null, '系统接口菜单');
-- 三级菜单
insert into sys_menu values(500,  '操作日志', 108, '1', 'operlog',    'monitor/operlog/index',    '', '', 1, 0, 'C', '0', '0', 'monitor:operlog:list',    'form',          'admin', current_timestamp, '', null, '操作日志菜单');
insert into sys_menu values(501,  '登录日志', 108, '2', 'logininfor', 'monitor/logininfor/index', '', '', 1, 0, 'C', '0', '0', 'monitor:logininfor:list', 'logininfor',    'admin', current_timestamp, '', null, '登录日志菜单');
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
    oper_time timestamp(0),
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
insert into sys_dict_type values(5,  '任务分组',     'sys_job_group',       '0', 'admin', current_timestamp, '', null, '任务分组列表');
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
insert into sys_dict_data values(10, 1,  '默认',             'default',        'sys_job_group',       '',   '',        'Y', '0', 'admin', current_timestamp, '', null, '默认分组');
insert into sys_dict_data values(11, 2,  '数据库',           'sqlalchemy',      'sys_job_group',       '',   '',        'N', '0', 'admin', current_timestamp, '', null, '数据库分组');
insert into sys_dict_data values(12, 3,  'redis',           'redis',  			'sys_job_group',       '',   '',        'N', '0', 'admin', current_timestamp, '', null, 'reids分组');
insert into sys_dict_data values(13, 1,  '默认',             'default',  		'sys_job_executor',    '',   '',        'N', '0', 'admin', current_timestamp, '', null, '线程池');
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
    login_time timestamp(0),
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
    job_name varchar(64) default '',
    job_group varchar(64) default 'default',
    job_executor varchar(64) default 'default',
    invoke_target varchar(500) not null,
    job_args varchar(255) default '',
    job_kwargs varchar(255) default '',
    cron_expression varchar(255) default '',
    misfire_policy varchar(20) default '3',
    concurrent char(1) default '1',
    status char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
    remark varchar(500) default '',
    primary key (job_id, job_name, job_group)
);
alter sequence sys_job_job_id_seq restart 100;
comment on column sys_job.job_id is '任务ID';
comment on column sys_job.job_name is '任务名称';
comment on column sys_job.job_group is '任务组名';
comment on column sys_job.job_executor is '任务执行器';
comment on column sys_job.invoke_target is '调用目标字符串';
comment on column sys_job.job_args is '位置参数';
comment on column sys_job.job_kwargs is '关键字参数';
comment on column sys_job.cron_expression is 'cron执行表达式';
comment on column sys_job.misfire_policy is '计划执行错误策略（1立即执行 2执行一次 3放弃执行）';
comment on column sys_job.concurrent is '是否并发执行（0允许 1禁止）';
comment on column sys_job.status is '状态（0正常 1暂停）';
comment on column sys_job.create_by is '创建者';
comment on column sys_job.create_time is '创建时间';
comment on column sys_job.update_by is '更新者';
comment on column sys_job.update_time is '更新时间';
comment on column sys_job.remark is '备注信息';
comment on table sys_job is '定时任务调度表';

-- ----------------------------
-- 初始化-定时任务调度表数据
-- ----------------------------
insert into sys_job values(1, '系统默认（无参）', 'default', 'default', 'module_task.scheduler_test.job', null,   null, '0/10 * * * * ?', '3', '1', '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(2, '系统默认（有参）', 'default', 'default', 'module_task.scheduler_test.job', 'test', null, '0/15 * * * * ?', '3', '1', '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(3, '系统默认（多参）', 'default', 'default', 'module_task.scheduler_test.job', 'new',  '{test: 111}', '0/20 * * * * ?', '3', '1', '1', 'admin', current_timestamp, '', null, '');
insert into sys_job values(4, '文件保留期限提醒', 'default', 'default', 'module_task.file_task.scan_retention_reminders', null, '{"remind_days": 7, "batch_size": 500}', '0 0 1 * * ?', '3', '1', '0', 'admin', current_timestamp, '', null, '每天扫描即将到期和已到期的受保护文件');
insert into sys_job values(5, '回收站永久清理', 'default', 'default', 'module_task.file_task.purge_recycle_bin', null, '{"retention_days": 30, "batch_size": 100}', '0 0 2 * * ?', '3', '1', '1', 'admin', current_timestamp, '', null, '永久清理超过保留期限的回收站文件，默认暂停');
insert into sys_job values(6, '文件存储对账', 'default', 'default', 'module_task.file_task.reconcile_file_storage', null, '{"check_hash": false}', '0 0 3 * * ?', '3', '1', '1', 'admin', current_timestamp, '', null, '校验文件信息表和本地存储一致性，默认暂停');

-- ----------------------------
-- 16、定时任务调度日志表
-- ----------------------------
drop table if exists sys_job_log;
create table sys_job_log (
    job_log_id bigserial not null,
    job_name varchar(64) not null,
    job_group varchar(64) not null,
    job_executor varchar(64) not null,
    invoke_target varchar(500) not null,
    job_args varchar(255) default '',
    job_kwargs varchar(255) default '',
    job_trigger varchar(255) default '',
    job_message varchar(500),
    status char(1) default '0',
    exception_info varchar(2000) default '',
    start_time timestamp(3),
    end_time timestamp(3),
    create_time timestamp(0),
    primary key (job_log_id)
);
comment on column sys_job_log.job_log_id is '任务日志ID';
comment on column sys_job_log.job_name is '任务名称';
comment on column sys_job_log.job_group is '任务组名';
comment on column sys_job_log.job_executor is '任务执行器';
comment on column sys_job_log.invoke_target is '调用目标字符串';
comment on column sys_job_log.job_args is '位置参数';
comment on column sys_job_log.job_kwargs is '关键字参数';
comment on column sys_job_log.job_trigger is '任务触发器';
comment on column sys_job_log.job_message is '日志信息';
comment on column sys_job_log.status is '执行状态（0正常 1失败）';
comment on column sys_job_log.exception_info is '异常信息';
comment on column sys_job_log.start_time is '执行开始时间';
comment on column sys_job_log.end_time is '执行结束时间';
comment on column sys_job_log.create_time is '创建时间';
comment on table sys_job_log is '定时任务调度日志表';

-- ----------------------------
-- 17、通知公告表
-- ----------------------------
drop table if exists sys_notice;
create table sys_notice (
    notice_id serial not null,
    notice_title varchar(50) not null,
    notice_type char(1) not null,
    notice_content bytea default null,
    status char(1) default '0',
    create_by varchar(64) default '',
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
-- 18、公告已读记录表
-- ----------------------------
drop table if exists sys_notice_read;
create table sys_notice_read (
    read_id bigserial not null,
    notice_id integer not null,
    user_id bigint not null,
    read_time timestamp(0) not null,
    primary key (read_id),
    constraint uk_user_notice unique (user_id, notice_id)
);
comment on column sys_notice_read.read_id is '已读主键';
comment on column sys_notice_read.notice_id is '公告ID';
comment on column sys_notice_read.user_id is '用户ID';
comment on column sys_notice_read.read_time is '阅读时间';
comment on table sys_notice_read is '公告已读记录表';

-- ----------------------------
-- 19、代码生成业务表
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
-- 20、代码生成业务表字段
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
    create_time timestamp(0),
    update_by varchar(64) default '',
    update_time timestamp(0),
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
-- 21、文件信息表
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
    create_time timestamp(0) not null,
    update_by varchar(64) default '',
    update_time timestamp(0) not null,
    expire_time timestamp(0),
    deleted_time timestamp(0),
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
-- 22、文件业务引用表
-- ----------------------------
drop table if exists sys_file_reference;
create table sys_file_reference (
    reference_id bigserial not null,
    file_id varchar(36) not null,
    business_type varchar(50) not null,
    business_id varchar(64) not null,
    business_name varchar(255),
    retention_expire_time timestamp(0),
    create_by varchar(64) default '',
    create_time timestamp(0) not null,
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
-- 23、文件业务保留策略表
-- ----------------------------
drop table if exists sys_file_retention_policy;
create table sys_file_retention_policy (
    business_type varchar(50) not null,
    retention_days integer not null,
    status char(1) not null default '0',
    remark varchar(500),
    create_by varchar(64) default '',
    create_time timestamp(0) not null,
    update_by varchar(64) default '',
    update_time timestamp(0) not null,
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
-- 24、文件保留期限提醒表
-- ----------------------------
drop table if exists sys_file_retention_notice;
create table sys_file_retention_notice (
    notice_id bigserial not null,
    file_id varchar(36) not null,
    notice_type varchar(20) not null,
    expire_time timestamp(0) not null,
    status char(1) not null default '0',
    create_time timestamp(0) not null,
    read_by varchar(64) default '',
    read_time timestamp(0),
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
-- 25、文件访问控制表
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
    expire_time timestamp(0),
    create_by varchar(64) default '',
    create_time timestamp(0) not null,
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
-- 26、文件访问审计表
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
    access_time timestamp(0) not null,
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
-- 27、文件存储对账任务表
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
    started_time timestamp(0) not null,
    finished_time timestamp(0),
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
-- 28、文件存储对账异常表
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
    first_seen_time timestamp(0) not null,
    last_seen_time timestamp(0) not null,
    handle_action varchar(32),
    handle_reason varchar(500),
    handled_by varchar(64),
    handled_time timestamp(0),
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
-- 29、插件信息表
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
  create_time        timestamp(0),
  update_by          varchar(64)    default '',
  update_time        timestamp(0),
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
-- 30、插件和菜单关联表
-- ----------------------------
drop table if exists sys_plugin_menu;
create table sys_plugin_menu (
  plugin_id          varchar(64)    not null,
  menu_id            bigint         not null,
  menu_key           varchar(255)   not null,
  create_time        timestamp(0),
  primary key (plugin_id, menu_id),
  constraint uk_sys_plugin_menu_key unique (plugin_id, menu_key)
);
comment on table sys_plugin_menu is '插件和菜单关联表';
comment on column sys_plugin_menu.plugin_id is '插件ID';
comment on column sys_plugin_menu.menu_id is '菜单ID';
comment on column sys_plugin_menu.menu_key is '插件内菜单自然键';
comment on column sys_plugin_menu.create_time is '创建时间';

-- ----------------------------
-- 31、插件 migration 执行历史表
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
  started_time        timestamp(0),
  finished_time       timestamp(0),
  create_time         timestamp(0),
  update_time         timestamp(0),
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
-- 32、插件配置表
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
  create_time        timestamp(0),
  update_time        timestamp(0),
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
-- 33、插件批量操作审计日志表
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
  create_time        timestamp(0),
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
                WHEN t.typtype = 'd'::"char" THEN format_type(t.typbasetype, NULL::integer)
                ELSE format_type(a.atttypid, NULL::integer)
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
       CURRENT_TIMESTAMP      AS create_time,
       CURRENT_TIMESTAMP      AS update_time
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
