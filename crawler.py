import logging
from datetime import datetime, timedelta
import os
import time
import schedule
from module import arxiv_reader, setup_logger
from post_paper import post_paper_file
from config_loader import config
import signal
import sys

logger = setup_logger()

# 从配置文件获取飞书URL列表
feishu_urls = config['feishu']['webhook_urls']


def should_run_today():
    """判断今天是否需要运行"""
    weekday = datetime.now().weekday()  # 0-6 表示周一到周日
    return weekday < 5  # 周一到周五返回True


def crawl_paper():
    # load arxiv class
    arxiv = arxiv_reader()

    # load topic words from config
    arxiv.get_your_interest(config['domain_keywords'])

    # go through all the newest articles
    arxiv.read_articles()

    # search the relevant article and record it in the record folder
    file_name = arxiv.find_match()
    return file_name


def crawl_and_post():
    """执行爬取和发送操作"""
    current_time = datetime.now()
    logger.info("=== 开始执行爬取和发送任务 ===")
    logger.info(f"当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"星期 {['一', '二', '三', '四', '五', '六', '日'][current_time.weekday()]}")

    if not should_run_today():
        logger.info("今天是周末，不执行发送操作")
        return

    try:
        #file_name ='/root/tangxinyu/article_crawler/record/20241118/20241118.txt'
        file_name = crawl_paper()
        if file_name and os.path.isfile(file_name):
            logger.info(f'开始处理文件：{file_name}')
            post_paper_file(file_name)
            logger.info(f'文件处理完成：{file_name}')
        else:
            logger.warning('没有找到文件或文件处理失败')
    except Exception as e:
        logger.error(f'处理失败: {str(e)}', exc_info=True)
    finally:
        logger.info("=== 任务执行结束 ===\n")


def signal_handler(signum, frame):
    """处理退出信号"""
    logger.info("收到退出信号，正在关闭程序...")
    sys.exit(0)


def get_next_run_time(schedule_time):
    """计算下次运行时间"""
    now = datetime.now()
    next_run = datetime.strptime(f"{now.date()} {schedule_time}", "%Y-%m-%d %H:%M")

    # 如果今天的执行时间已经过了，设置为明天
    if next_run <= now:
        next_run += timedelta(days=1)

    return next_run


def daily_crawl():
    """设置每日任务"""
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 从配置文件获取发送时间
    daily_post_time = config['schedule']['daily_post_time']
    logger.info(f"定时任务已启动，将在每天 {daily_post_time} 执行")

    # 设置每日任务
    schedule.every().day.at(daily_post_time).do(crawl_and_post)

    try:
        while True:
            # 计算到下次执行的等待时间
            next_run = get_next_run_time(daily_post_time)
            wait_seconds = (next_run - datetime.now()).total_seconds()

            # 记录下次执行时间
            logger.info(f"下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"等待时间: {wait_seconds:.0f} 秒")

            # 使用较短的间隔检查，以便能够及时响应退出信号
            while wait_seconds > 0:
                schedule.run_pending()
                sleep_time = min(10, wait_seconds)  # 最多休眠10秒
                time.sleep(sleep_time)
                wait_seconds -= sleep_time

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}", exc_info=True)
    finally:
        logger.info("程序已退出")


if __name__ == "__main__":
    daily_crawl()
