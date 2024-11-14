import requests
import feedparser
import datetime
import os
import json


def format_date(days=0):
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y%m%d')

def is_related_by_keyword(title, summary, keywords):
        text = title.lower() + " " + summary.lower()
        return any(keyword.lower() in text for keyword in keywords)

class arxiv_reader():
    """
    feedparser Version
    """
    def __init__(self) -> None:
        self.articles = []
        self.match_articles = []
        self.today_date = format_date(1)
        self.yesterday_date = format_date(2)
        self.url = f'http://export.arxiv.org/api/query?search_query=(cat:"cs.CL" OR cat:"cs.AI") AND (submittedDate:[{self.yesterday_date}+TO+{self.today_date}])&sortBy=submittedDate&sortOrder=descending&max_results=1000'
        super().__init__()

    def get_your_interest(self, interests):
        """
        interest is a list. e.g. interests = ["image captioning", "visual question answering"]
        """
        self.interests = interests
        
    def read_articles(self):
        """
        The article information is stored in a dictionary. The form looks like {"title": title, "summary": summary, "link": link}
        """
        # Parse the feed using feedparser
        response = requests.get(self.url)
        feed = feedparser.parse(response.content)

        #Store article title and summary into a dictionary, store article into a articles list
        for entry in feed.entries:
            article = {}
            article["title"] = entry.title
            article["link"] = entry.link
            article["summary"] = entry.summary
            self.articles.append(article)
        
    
    def print_out(self):
        """
        Print out the article information stored in the list
        """
        for entry in self.articles:
            print("Title:", entry["title"])
            print("Summary:", entry["summary"])
            print("Link:", entry["link"])
            print("\n")

    def find_match(self):
        folder_path = "record/" + str(datetime.datetime.now().strftime('%Y%m%d'))
        os.makedirs(folder_path, exist_ok=True)
        text_path = os.path.join(folder_path, '%s.txt' %(str(datetime.datetime.now().strftime('%Y%m%d'))))
        # self.post_to_robot(None) !!!
        for entry in self.articles:
            title = entry["title"]
            summary = entry["summary"]
            link = entry["link"]
            if is_related_by_keyword(title, summary, self.interests):
                llm_sum = self.query_gpt4o(title + '\n' + summary)
                clean_sum = llm_sum.strip('`').replace('\n', '').strip('json').strip().replace("'", '"')
                try:
                    json_paper = json.loads(clean_sum)
                    print(json_paper)
                except json.JSONDecodeError as e:
                    continue
                with open(text_path, "a") as file:
                    #file.write("Tittle: " + title + "\n")
                    #file.write("Summary: "+ summary + "\n")
                    #file.write("Link:" + link + "\n")
                    #file.write("\n")
                    json_paper['标题'] = f"[{title}]({link})".replace('\n', '').strip()
                    json_str = json.dumps(json_paper, ensure_ascii=False)
                    file.write(json_str + '\n')
                self.match_articles.append(entry)
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

    def query_gpt4o(self, query_message):
        prompt = f"请根据文章的摘要，判断一下这个文章是否适合一位AI算法工程师阅读，总结中文摘要，要求摘要只有一句话，只用讲论文干了什么，并给出推荐阅读的分数，分数范围为1-5分。分数标准：如果是具体领域的AI应用，则应该打低分，例如医学、生物学领域的就应该打低分；如果方法的创新性强，有巨大的研究、学习价值，则打高分。给出的论文内容如下：{query_message}\n" + "你不需要给出推荐理由，直接输出json格式的结果：{'论文摘要': '中文摘要', '推荐分数': '1分'}"
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
            "max_tokens": 2000,
        }

        response = requests.post(
            "https://gpt-4o-future-array.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview", headers=headers, json=payload
        )

        final_response = (response.json()
            .get("choices")[0]
            .get("message")
            .get("content")
            .replace("\n\n", "\n")
        )
        return final_response
