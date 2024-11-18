import requests
import json
from config_loader import config


def cut_str(string, max_len=150):
    if len(string) <= max_len:
        return string
    return string[:max_len] + "..."


def post_to_robot(paper_infos, feishu_url, interest_topic):
    feishu_format = {
        "type": "template",
        "data": {
            "template_id": "AAqDotEjrm0Xo",
            "template_version_name": "1.0.11",
            "template_variable": {
                "field": interest_topic,
                "article_set": paper_infos,
            },
        },
    }
    headers = {"Content-Type": "application/json"}
    data = {"msg_type": "interactive", "card": feishu_format}

    response = requests.post(feishu_url, headers=headers, data=json.dumps(data))
    # print(response.json().get('msg'))


def judge_accept_paper(paper_infos):
    """判断论文是否接受

    Args:
        paper_infos: 包含论文信息的字典
    Returns:
        bool: 是否接受该论文
    """
    # 转换分数为数字进行比较
    try:
        # 如果是字符串,尝试提取数字
        if isinstance(paper_infos['article_score'], str):
            score = float(paper_infos['article_score'].replace('分', ''))
        else:
            score = float(paper_infos['article_score'])

        # 分数低于3分的论文不接受
        return score > 3.0

    except (ValueError, TypeError) as e:
        print(f"分数解析错误: {paper_infos['article_score']}, 错误: {e}")
        return False  # 解析失败时默认不接受


def remove_article_score(data):
    # Remove 'article_score' key from each item
    for item in data:
        if 'article_score' in item:
            del item['article_score']


def read_paper_file(file_name):
    paper_list = []
    with open(file_name, 'r', encoding='utf-8') as f:
        for line in f:
            var = {}
            paper = json.loads(line.strip())
            summary = cut_str(paper["论文摘要"])

            # 处理多个领域标签
            domains_info = paper['领域']
            tag_colors = config['tag_colors']

            tags = []
            for domain, keywords in domains_info.items():
                color = tag_colors.get(domain, "grey")
                keywords_str = ",".join(keywords)
                tag_text = f"{domain}({keywords_str})"
                tags.append(f"<text_tag color='{color}'>{tag_text}</text_tag>")

            var = {
                "article_sum": summary,
                "article_title": paper["标题"],
                "article_score": paper["推荐分数"],
                "tag": " ".join(tags),
                "domains": domains_info.keys(),
            }

            if judge_accept_paper(var):
                paper_list.append(var)

    return paper_list


def group_papers_by_domain(papers):
    """按领域对论文进行分组"""
    domain_priority = config['domain_priority']
    domain_groups = {domain: [] for domain in domain_priority.keys()}

    for paper in papers:
        matched_domains = paper["domains"]
        if matched_domains:
            primary_domain = min(matched_domains, key=lambda x: domain_priority.get(x, 999))
            domain_groups[primary_domain].append(paper)

    # 对每个领域内的论文按分数排序
    for domain in domain_groups:
        domain_groups[domain].sort(key=lambda x: -float(x.get('article_score', '0')))
        # 清理临时字段
        for paper in domain_groups[domain]:
            del paper["domains"]
            remove_article_score([paper])

    return domain_groups


def post_paper_file(file_name, feishu_url):
    papers = read_paper_file(file_name)
    domain_groups = group_papers_by_domain(papers)

    domain_priority = config['domain_priority']
    for domain in sorted(domain_priority.keys(), key=lambda x: domain_priority[x]):
        if domain_groups[domain]:  # 只发送有论文的领域
            post_to_robot(domain_groups[domain][:30], feishu_url, domain)
