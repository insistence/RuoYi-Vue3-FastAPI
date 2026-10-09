CREATE TABLE ruoyi_plugin_task_demo (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    description VARCHAR(500) NOT NULL DEFAULT '',
    status VARCHAR(4) NOT NULL DEFAULT 'todo',
    created_at TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    CONSTRAINT ck_task_demo_status CHECK (status IN ('todo', 'done'))
);
