import os
from fastapi import UploadFile


class CommonService:
    """
    通用模块服务层
    """

    @classmethod
    def upload_service(cls, path: str, task_path: str, upload_id: str, file: UploadFile):

        filepath = os.path.join(path, task_path, upload_id, f'{file.filename}')
        with open(filepath, 'wb') as f:
            # 流式写出大型文件，这里的10代表10MB
            for chunk in iter(lambda: file.file.read(1024 * 1024 * 10), b''):
                f.write(chunk)

