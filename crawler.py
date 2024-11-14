from module import arxiv_reader
from post_paper import post_paper_file
import schedule
import os
import time

feishu_url = "https://open.f.mioffice.cn/open-apis/bot/v2/hook/a8862209-8d1f-4f0b-b3f7-f63278840fd4"
interest_topic = ["LLM", "LLMs", "language model", "language models", "music", "role-play"]
daily_post_time = "01:10"

def crawl_paper():
    # load arxiv class
    arxiv = arxiv_reader()

    # load topic words 
    arxiv.get_your_interest(interest_topic)

    # go through all the newest articles
    arxiv.read_articles()

    # search the relevant article and record it in the record folder
    file_name = arxiv.find_match()
    return file_name

def crawl_and_post():
    print('start running!')
    file_name = None
    for i in range(5):
        try:
            file_name = crawl_paper()
            break
        except:
            continue
    if file_name is None:
        print('今日论文处理失败！')
        return

    if os.path.isfile(file_name):
        post_paper_file(file_name, feishu_url)
    else:
        print('没有找到文件路径')

def daily_crawl():
    schedule.every().day.at(daily_post_time).do(crawl_and_post)
    while True:
        schedule.run_pending()
        time.sleep(10)

daily_crawl()
