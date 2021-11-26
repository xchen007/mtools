from loguru import logger
import time
import os
from .settings import BASE_DIR as project_path

def l_logger(app_name, module_name=''):
    # 如果是部分脱离整体 app 进行日志记录, 就加上一个参数, 不填都加到 app 整体日志下
    log_name = module_name if module_name else app_name
    log_path = f"{project_path}/apps/logs/{app_name}/{log_name}_log.log"

    logger.add(log_path,
               rotation="1 week",  # 每周生成新文件
               encoding="utf-8",  # 写入文件编码
               enqueue=True,  # 异步写入
               backtrace=True,  #
               diagnose=True,  # 显示堆栈报错信息
               retention="10 days"  # 保存时间
               )
    return logger

@logger.catch
def test_1():
    return 1/0

if __name__ == '__main__':
    logger = l_logger('personal')
    logger.info('test')
    logger.debug('test')
    logger.error('test')

    test_1()



