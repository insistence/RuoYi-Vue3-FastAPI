from fastapi import FastAPI
from sub_applications.staticfiles import mount_staticfiles


def handle_sub_applications(app: FastAPI):
    """
    全局处理子应用挂载
    """
    # 挂载静态文件
    mount_staticfiles(app)
