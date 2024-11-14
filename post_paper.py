import requests
import json

def cut_str(string, max_len=150):
    if len(string) <= max_len:
        return string
    return string[:max_len] + "..."

def post_to_robot(paper_infos, feishu_url):
    feishu_format = {
      "type": "template",
      "data": {
        "template_id": "ctp_AA00oqPWTLqU",
        "template_version_name": "1.0.0",
        "template_variable": {"article_set":paper_infos},
      }
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = {"msg_type":"interactive","card": feishu_format}

    response = requests.post(feishu_url, headers=headers, data=json.dumps(data))
    print(response.json().get('msg'))

def judge_accept_paper(paper_infos):
    reject_scores = ['1', '2', '3']
    for score in reject_scores:
        if score in paper_infos['article_score']:
            return False
    return True


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
            var = {"article_sum":summary, "article_title":paper["标题"], "article_score":paper["推荐分数"]}
            if judge_accept_paper(var):
                paper_list.append(var)
    sorted_paper = sorted(paper_list, key=lambda x: x.get('article_score', 0), reverse=True)
    remove_article_score(sorted_paper)
    return sorted_paper

def post_paper_file(file_name, feishu_url):
    papers = read_paper_file(file_name)
    post_to_robot(papers[:60], feishu_url)
