from fastapi.staticfiles import StaticFiles
from server import app
from config.env import UploadConfig


# 挂载静态文件路径
app.mount(f"{UploadConfig.UPLOAD_PREFIX}", StaticFiles(directory=f"{UploadConfig.UPLOAD_PATH}"), name="profile")
