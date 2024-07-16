from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from config.env import UploadConfig


def mount_staticfiles(app: FastAPI):
    """
    挂载静态文件
    """
    app.mount(f'{UploadConfig.UPLOAD_PREFIX}', StaticFiles(directory=f'{UploadConfig.UPLOAD_PATH}'), name='profile')
