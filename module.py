import requests
import feedparser
import datetime
import os
import json
from zhipuai import ZhipuAI
from config_loader import config
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import random
from functools import wraps
from requests.exceptions import RequestException
import logging


# 设置日志格式
def setup_logger():
    # 创建logs目录（如果不存在）
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 生成日志文件名（使用当前日期）
    log_file = os.path.join(log_dir, f'crawler_{datetime.datetime.now().strftime("%Y%m%d")}.log')

    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),  # 同时输出到控制台
        ],
    )

    return logging.getLogger(__name__)


logger = setup_logger()


def calculate_final_score(score_dict):
    """计算加权最终分数

    Args:
        score_dict: 包含各部分分数的字典
    Returns:
        float: 计算后的加权最终分数
    """
    try:
        if isinstance(score_dict, dict):
            # 定义各部分权重
            weights = {
                'part1': 0.15,  # 研究问题/假设
                'part2': 0.20,  # 研究方法
                'part3': 0.20,  # 结果
                'part4': 0.15,  # 结论
                'part5': 0.20,  # 原创性和重要性
                'part6': 0.10,  # 写作质量
            }

            # 计算加权分数
            weighted_score = sum(
                score_dict.get(part, 0) * weight for part, weight in weights.items()
            )

            # 保留两位小数
            return round(weighted_score, 2)

        elif isinstance(score_dict, str):
            return float(score_dict.replace('分', ''))
        elif isinstance(score_dict, (int, float)):
            return float(score_dict)
        else:
            print(f"未知的分数格式: {score_dict}")
            return 0.0
    except Exception as e:
        print(f"分数计算错误: {score_dict}, 错误: {e}")
        return 0.0


def retry_with_exponential_backoff(
    max_retries=3, initial_delay=1, exponential_base=2, jitter=True, exceptions=(Exception,)
):
    """
    重试装饰器，使用指数退避策略

    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间(秒)
        exponential_base: 指数基数
        jitter: 是否添加随机抖动
        exceptions: 需要重试的异常类型
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_count = 0
            delay = initial_delay

            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(f"达到最大重试次数 {max_retries}, 最后一次错误: {str(e)}")
                        raise  # 重新抛出异常

                    # 计算延迟时间
                    delay_with_jitter = delay
                    if jitter:
                        delay_with_jitter *= 1 + random.random()

                    logger.warning(
                        f"操作失败: {str(e)}. 第 {retry_count} 次重试, "
                        f"等待 {delay_with_jitter:.2f} 秒..."
                    )

                    time.sleep(delay_with_jitter)
                    delay *= exponential_base  # 指数增加延迟时间

        return wrapper

    return decorator


def format_date(days=0):
    """返回指定天数前的日期，格式为YYYYMMDD"""
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')


def is_related_by_keyword(title, summary, domain_keywords):
    """
    检查文章是否与任何领域相关

    Args:
        title (str): 文章标题
        summary (str): 文章摘要
        domain_keywords (dict): 领域关键词字典，格式为 {"领域": [关键词列表]}

    Returns:
        bool: 是否匹配任何领域的关键词
    """
    text = title.lower() + " " + summary.lower()

    # 检查是否匹配任何领域的任何关键词
    return any(
        any(keyword.lower() in text for keyword in keywords)
        for keywords in domain_keywords.values()
    )


def get_date_range():
    """根据当前工作日确定检索的日期范围"""
    current_date = datetime.datetime.now()
    weekday = current_date.weekday()  # 0-6 表示周一到周日

    if weekday == 0:  # 周一
        # 检索周六到周一的论文
        start_date = current_date - datetime.timedelta(days=3)  # 从周六开始
        end_date = current_date
        logger.info(
            f"今天是周一，检索范围：{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}"
        )
    else:  # 周二到周五
        # 只检索前一天的论文
        start_date = current_date - datetime.timedelta(days=1)
        end_date = current_date
        logger.info(
            f"今天是周{weekday + 1}，检索范围：{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}"
        )

    return start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')


class arxiv_reader:
    """
    feedparser Version
    """

    def __init__(self) -> None:
        logger.info(
            f"\n开始执行论文检索 - 当前时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.articles = []
        self.match_articles = []

        # 获取日期范围
        self.yesterday_date, self.today_date = get_date_range()

        self.domain_urls = {}
        self.file_lock = threading.Lock()

        # 为每个领域构建专门的URL
        for domain, keywords in config['domain_keywords'].items():
            # 从配置中获取该领域的类别
            categories = config['categories'][domain]
            category_query = ' OR '.join(f'cat:"{cat}"' for cat in categories)

            # 构建该领域的查询URL
            url = (
                'http://export.arxiv.org/api/query?search_query='
                + f'({category_query})'
                + f' AND lastUpdatedDate:[{self.yesterday_date}0000 TO {self.today_date}2359]'
                + '&sortBy=lastUpdatedDate&sortOrder=descending&max_results=1000'
            )
            self.domain_urls[domain] = url
            logger.info(f"领域 {domain} 的检索URL: {url}")

    def get_your_interest(self, domain_keywords):
        """
        interest is a list. e.g. interests = ["image captioning", "visual question answering"]
        """
        # 将所有关键词展平为一个列表，用于is_related_by_keyword函数
        self.domain_keywords = domain_keywords
        self.interests = [keyword for keywords in domain_keywords.values() for keyword in keywords]

    def read_articles(self):
        """读取每个领域的最新论文"""
        for domain, url in self.domain_urls.items():
            domain_articles = self._fetch_articles(url)
            for article in domain_articles:
                article['domain'] = domain  # 标记论文属于哪个领域
                self.articles.append(article)

    def _fetch_articles(self, url):
        """从指定URL获取论文"""
        # Parse the feed using feedparser
        response = requests.get(url)
        feed = feedparser.parse(response.content)

        # Store article title and summary into a dictionary, store article into a articles list
        articles = []
        for entry in feed.entries:
            article = {}
            article["title"] = entry.title
            article["link"] = entry.link
            article["summary"] = entry.summary
            articles.append(article)
        return articles

    def print_out(self):
        """
        Print out the article information stored in the list
        """
        for entry in self.articles:
            print("Title:", entry["title"])
            print("Summary:", entry["summary"])
            print("Link:", entry["link"])
            print("\n")

    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1,
        exceptions=(
            RequestException,
            json.JSONDecodeError,
            Exception,  # 捕获所有异常
        ),
    )
    def query_glm(self, title, query_message):
        """带重试机制的GLM查询"""
        GLM_API_KEY = '127cf47901680b0c87c693e2931a3493.9DII9LMu9rKMn4Is'
        client = ZhipuAI(api_key=GLM_API_KEY)
        prompt = f'''
            你是一个论文评审专家，可以概括论文，发现论文的创新点，并且根据论文的摘要给论文打分。你现在需要用中文用一句话概括出论文的要点，并给摘要作出评分。你的回答应该是
            1. 准确、完整、突出重点。
            2. 简明扼要、逻辑清晰。
            
            请根据part1. "研究问题/假设"、part2. "研究方法"、part3. "结果"、part4. "结论"、part5. "原创性和重要性"、part6. "写作质量"，对这6个方面给论文打分，分数范围为1-5分。每个方面的打分标准如下：
            part1. 研究问题/假设：
                1分：摘要中没有明确提出研究问题或假设，或者问题表述模糊不清，难以理解其研究目的。
                2分：摘要中提到了研究问题或假设，但问题不够具体，缺乏明确的研究目标，或者假设与现有理论或实践关联性不强。
                3分：摘要中明确提出了研究问题或假设，问题具体且与研究目的紧密相关，假设基于合理的理论基础。
                4分：摘要中的研究问题或假设非常明确，与研究目的高度一致，假设具有创新性或实践意义。
                5分：摘要中的研究问题或假设极具创新性，对现有理论或实践提出了新的挑战或视角。
            part2. 研究方法：
                1分：摘要中未描述研究方法，或者方法描述过于简略，无法判断其合理性。
                2分：摘要中提到了研究方法，但描述不够详细，难以评估方法的适用性。
                3分：摘要中描述了研究方法，方法合理，但可能缺乏一些关键细节。
                4分：摘要中详细描述了研究方法，包括样本选择、数据收集和分析过程，方法适合于解决研究问题。
                5分：摘要中不仅详细描述了研究方法，而且方法创新，具有科学性和严谨性。
            part3. 结果：
                1分：摘要中未提供结果或结果描述不清晰，无法判断研究的有效性。
                2分：摘要中提到了一些结果，但缺乏详细数据和解释，难以评估结果的意义。
                3分：摘要中提供了清晰的结果描述，数据基本完整，但可能缺乏深入的解释。
                4分：摘要中不仅提供了清晰的结果描述，而且对结果进行了深入的解释，结果具有一定的说服力。
                5分：摘要中的结果描述详尽，数据完整，解释深入，结果具有显著性和重要意义。
            part4. 结论：
                1分：摘要中未提供结论或结论与结果不相关，无法判断研究的贡献。
                2分：结论简单，与研究结果基本一致，但缺乏对结果的深入分析和讨论。
                3分：结论合理，与研究结果一致，并有一定深度，但可能缺乏对理论和实践的贡献。
                4分：结论与研究结果高度一致，深入且具有启发性，对理论和实践有显著贡献。
                5分：结论与研究结果高度一致，深入、创新且具有广泛应用价值，对领域发展有重要影响。
            part5. 原创性和重要性：
                1分：摘要中没有显示出原创性，研究问题或方法缺乏重要性。
                2分：有一定的原创性，研究问题或方法有一定的重要性，但可能不是非常显著。
                3分：原创性适中，研究问题或方法具有重要性，对现有研究有所贡献。
                4分：原创性强，研究问题或方法具有重大理论或实践意义，对领域发展有重要影响。
                5分：具有高度原创性，研究问题或方法具有深远的影响，推动了领域的发展。
            part6. 写作质量：
                1分：摘要写作混乱，存在大量语法或拼写错误，语言表达不清晰。
                2分：摘要基本清晰，但存在一些语法或拼写错误，语言表达不够精炼。
                3分：摘要清晰，语言流畅，符合学术规范，但可能缺乏一些修辞上的精炼。
                4分：摘要非常清晰，语言精炼，表达准确，符合学术写作标准。
                5分：摘要极其精炼、准确，语言表达无懈可击，体现了高水平的学术写作能力。
        
            论文的标题是：{title}
            论文的摘要如下：{query_message}
            你不需要给出推荐理由，也不需要加“分”，直接给出数字，直接输出json格式的结果：{{'论文摘要': '一句话论文要点', 'part1分数': '1', 'part2分数': '1', 'part3分数': '1', 'part4分数': '1', 'part5分数': '1', 'part6分数': '1'}}
            '''

        try:
            response = client.chat.completions.create(
                model="GLM-4-Flash",
                messages=[
                    {"role": "user", "content": f"{prompt}"},
                ],
                temperature=0.3,
                top_p=0.85,
            )
            return response.choices[0].message.content.replace("\n\n", "\n")
        except Exception as e:
            logger.error(f"GLM API调用失败: {str(e)}")
            raise

    def process_single_article(self, entry, text_path):
        time.sleep(2)  # 添加延时
        """处理单篇文章，包含重试逻辑"""
        title = entry["title"]
        summary = entry["summary"]
        link = entry["link"]

        try:
            logger.info(f"开始处理文章: {title}")

            # 获取匹配的领域
            matched_domains = self.get_related_domains(title, summary, self.domain_keywords)

            if matched_domains:  # 如果有匹配的领域
                try:
                    # GLM查询已经包含重试机制
                    llm_sum = self.query_glm(title, summary)
                    clean_sum = (
                        llm_sum.strip('`').replace('\n', '').strip('json').strip().replace("'", '"')
                    )

                    json_paper = json.loads(clean_sum)
                    # 计算最终分数并添加到json中
                    if (
                        'part1分数' in json_paper
                        and 'part2分数' in json_paper
                        and 'part3分数' in json_paper
                        and 'part4分数' in json_paper
                        and 'part5分数' in json_paper
                        and 'part6分数' in json_paper
                    ):  # 确保是新格式的分数
                        score_dict = {
                            'part1': float(json_paper['part1分数']),
                            'part2': float(json_paper['part2分数']),
                            'part3': float(json_paper['part3分数']),
                            'part4': float(json_paper['part4分数']),
                            'part5': float(json_paper['part5分数']),
                            'part6': float(json_paper['part6分数']),
                        }
                        final_score = calculate_final_score(score_dict)

                    # 添加最终分数到json
                    json_paper['推荐分数'] = final_score

                    logger.info(f"成功处理文章: {title}")

                    # 添加标题领域信息
                    json_paper['标题'] = f"[{title}]({link})".replace('\n', '').strip()
                    json_paper['领域'] = matched_domains

                    # 使用锁保护文件写入
                    with self.file_lock:
                        with open(text_path, "a") as file:
                            json_str = json.dumps(json_paper, ensure_ascii=False)
                            file.write(json_str + '\n')

                    return entry
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {title}, 错误: {e}")
                    return None
                except Exception as e:
                    logger.error(f"处理文章时发生错误: {title}, 错误: {e}")
                    return None
        except Exception as e:
            logger.error(f"处理文章失败: {title}, 错误: {e}")
            return None

        return None

    def find_match(self):
        folder_path = "record/" + str(datetime.datetime.now().strftime('%Y%m%d'))
        os.makedirs(folder_path, exist_ok=True)
        text_path = os.path.join(
            folder_path, '%s.txt' % (str(datetime.datetime.now().strftime('%Y%m%d')))
        )

        # 创建新文件
        with open(text_path, "w") as file:
            file.write("")

        # 使用线程池并行处理文章
        with ThreadPoolExecutor(max_workers=10) as executor:  # 可以调整max_workers的数量
            # 提交所有任务
            future_to_article = {
                executor.submit(self.process_single_article, entry, text_path): entry
                for entry in self.articles
            }

            # 收集成功处理的文章
            self.match_articles = []
            for future in as_completed(future_to_article):
                if future.result():
                    self.match_articles.append(future.result())

        return text_path

    def print_out_matching(self):
        """
        Print out the article information stored in the list
        """
        for entry in self.match_articles:
            print("Title:", entry["title"])
            print("Summary:", entry["summary"])
            print("Link:", entry["link"])
            print("\n")

    def query_gpt4o(self, title, query_message):
        # prompt = (
        #     f"请根据文章的摘要，判断一下这个文章是否适合一位AI算法工程师阅读，总结中文摘要，要求摘要只有一句话，只用讲论文干了什么，并给出推荐阅读的分数，分数范围为1-5分。分数标准：如果是具体领域的AI应用，则应该打低分，例如医学、生物学领域的就应该打低分；如果方法的创新性强，有巨大的研究、学习价值，则打高分。出的论文内容如下：{query_message}\n"
        #     + "你不需要给出推荐理由，直接输出json格式的结果：{'论文摘要': '中文摘要', '推荐分数': '1分'}"
        # )
        prompt = f'''
            你是一个论文评审专家，可以概括论文，发现论文的创新点，并且根据论文的摘要给论文打分。你现在需要用中文用一句话概括出论文的要点，并给摘要作出评分。你的回答应该是
            1. 准确、完整、突出重点。
            2. 简明扼要、逻辑清晰。
            
            请根据研究问题/假设、研究方法、结果、结论、原创性和重要性、写作质量如下6个方面给论文打分，分数范围为1-5分。每个方面的权重和打分标准如下：
            part1. 研究问题/假设（15%）：
                1分：摘要中没有明确提出研究问题或假设，或者问题表述模糊不清，难以理解其研究目的。
                2分：摘要中提到了研究问题或假设，但问题不够具体，缺乏明确的研究目标，或者假设与现有理论或实践关联性不强。
                3分：摘要中明确提出了研究问题或假设，问题具体且与研究目的紧密相关，假设基于合理的理论基础。
                4分：摘要中的研究问题或假设非常明确，与研究目的高度一致，假设具有创新性或实践意义。
                5分：摘要中的研究问题或假设极具创新性，对现有理论或实践提出了新的挑战或视角。
            part2. 研究方法（20%）：
                1分：摘要中未描述研究方法，或者方法描述过于简略，无法判断其合理性。
                2分：摘要中提到了研究方法，但描述不够详细，难以评估方法的适用性。
                3分：摘要中描述了研究方法，方法合理，但可能缺乏一些关键细节。
                4分：摘要中详细描述了研究方法，包括样本选择、数据收集和分析过程，方法适合于解决研究问题。
                5分：摘要中不仅详细描述了研究方法，而且方法创新，具有科学性和严谨性。
            part3. 结果（20%）：
                1分：摘要中未提供结果或结果描述不清晰，无法判断研究的有效性。
                2分：摘要中提到了一些结果，但缺乏详细数据和解释，难以评估结果的意义。
                3分：摘要中提供了清晰的结果描述，数据基本完整，但可能缺乏深入的解释。
                4分：摘要中不仅提供了清晰的结果描述，而且对结果进行了深入的解释，结果具有一定的说服力。
                5分：摘要中的结果描述详尽，数据完整，解释深入，结果具有显著性和重要意义。
            part4. 结论（15%）：
                1分：摘要中未提供结论或结论与结果不相关，无法判断研究的贡献。
                2分：结论简单，与研究结果基本一致，但缺乏对结果的深入分析和讨论。
                3分：结论合理，与研究结果一致，并有一定深度，但可能缺乏对理论和实践的贡献。
                4分：结论与研究结果高度一致，深入且具有启发性，对理论和实践有显著贡献。
                5分：结论与研究结果高度一致，深入、创新且具有广泛应用价值，对领域发展有重要影响。
            part5. 原创性和重要性（20%）：
                1分：摘要中没有显示出原创性，研究问题或方法缺乏重要性。
                2分：有一定的原创性，研究问题或方法有一定的重要性，但可能不是非常显著。
                3分：原创性适中，研究问题或方法具有重要性，对现有研究有所贡献。
                4分：原创性强，研究问题或方法具有重大理论或实践意义，对领域发展有重要影响。
                5分：具有高度原创性，研究问题或方法具有深远的影响，推动了领域的发展。
            part6. 写作质量（10%）：
                1分：摘要写作混乱，存在大量语法或拼写错误，语言表达不清晰。
                2分：摘要基本清晰，但存在一些语法或拼写错误，语言表达不够精炼。
                3分：摘要清晰，语言流畅，符合学术规范，但可能缺乏一些修辞上的精炼。
                4分：摘要非常清晰，语言精炼，表达准确，符合学术写作标准。
                5分：摘要极其精炼、准确，语言表达无懈可击，体现了高水平的学术写作能力。
            最终分数的计算公式是：part1 * 0.15 + part2 * 0.2 + part3 * 0.2 + part4 * 0.15 + part5 * 0.2 + part6 * 0.1
            
            论文的标题是：{title}
            论文的摘要如下：{query_message}
            
            你不需要给出推荐理由，直接输出json格式的结果：{{'论文摘要': '一句话论文要点', '推荐分数': '1分'}}
            '''
        headers = {
            "Content-Type": "application/json",
            "api-key": "d769479c4cf94dd08bc10c42dfdfab53",
        }
        message = {
            "role": "user",
            "content": [{"type": "text", "text": f"{prompt}"}],
        }

        payload = {
            "model": "gpt-4o",
            "messages": [message],
            "max_tokens": 4000,
        }

        response = requests.post(
            "https://gpt-4o-future-array.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview",
            headers=headers,
            json=payload,
        )

        final_response = (
            response.json().get("choices")[0].get("message").get("content").replace("\n\n", "\n")
        )
        return final_response

    def get_related_domains(self, title, summary, domain_keywords):
        """
        获取文章匹配的所有领域及其对应的关键词

        Args:
            title (str): 文章标题
            summary (str): 文章摘要
            domain_keywords (dict): 领域关键词字典，格式为 {"领域": [关键词列表]}

        Returns:
            dict: 匹配的领域及其关键词，格式为 {"领域": [匹配的关键词列表]}
        """
        text = title.lower() + " " + summary.lower()
        matched_info = {}

        for domain, keywords in domain_keywords.items():
            matched_keywords = [kw for kw in keywords if kw.lower() in text]
            if matched_keywords:
                matched_info[domain] = matched_keywords

        return matched_info
