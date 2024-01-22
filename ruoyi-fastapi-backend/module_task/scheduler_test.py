from datetime import datetime


def job(*args, **kwargs):
    print(args)
    print(kwargs)
    print(f"{datetime.now()}执行了")
