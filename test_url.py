import requests
import json
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_post_to_robot():
    # 测试数据
    paper_infos = [
        {
            # "field": "**AI(machine learning)**",
            "article_title": "[Metacognition for Unknown Situations and Environments (MUSE)](http://arxiv.org/abs/2411.13537v1)",
            "tag": "<text_tag color='red'>这是一个绿色文本 </text_tag>",
            "article_sum": "This is a test paper summary",
        },
        {
            # "field": "**AI(machine learning)**",
            "article_title": "[Metacognition for Unknown Situations and Environments (MUSE)](http://arxiv.org/abs/2411.13537v1)",
            "tag": '<text_tag color="red">标签文本</text_tag>',
            "article_sum": "This is a test paper summary",
        },
    ]

    # webhook配置
    webhook_config = {
        "url": "https://open.f.mioffice.cn/open-apis/bot/v2/hook/2a54c775-79de-4dab-ba84-949cc9c2542b",
        "template_id": "AAqjm6DzbLfjw",
        "template_version": "1.0.14",
    }

    interest_topic = "AI"
    date_title = "2024-03-14"

    try:
        # 构造请求数据
        feishu_format = {
            "type": "template",
            "data": {
                "template_id": webhook_config['template_id'],
                "template_version_name": webhook_config['template_version'],
                "template_variable": {
                    "field": interest_topic,
                    "date": date_title,
                    "object_list_4": paper_infos,
                },
            },
        }
        print(feishu_format)

        headers = {"Content-Type": "application/json"}
        data = {"msg_type": "interactive", "card": feishu_format}

        # 发送请求
        response = requests.post(webhook_config['url'], headers=headers, data=json.dumps(data))

        # 检查响应
        if response.status_code == 200:
            logger.info("测试成功: 消息已发送")
            logger.info(f"响应内容: {response.text}")
        else:
            logger.error(f"测试失败: HTTP {response.status_code}")
            logger.error(f"错误信息: {response.text}")

    except Exception as e:
        logger.error(f"测试出错: {str(e)}")


def main():
    print("开始测试飞书机器人消息发送...")
    test_post_to_robot()
    print("测试完成")


if __name__ == "__main__":
    main()
