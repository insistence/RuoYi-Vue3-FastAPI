ALTER TABLE ruoyi_plugin_task_demo
    ADD COLUMN priority VARCHAR(6) NOT NULL DEFAULT 'normal',
    ADD CONSTRAINT ck_task_demo_priority CHECK (priority IN ('normal', 'high'));
