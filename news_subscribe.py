from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from dotenv import load_dotenv
import re
import time

# 加载环境变量（读取.env文件中的配置）
load_dotenv()
app = Flask(__name__)
CORS(app)  # 解决跨域问题

# -------------------------- 核心配置 --------------------------
# 魔塔AI配置
MOTA_API_URL = os.getenv("MOTA_API_URL")
MOTA_API_KEY = os.getenv("MOTA_API_KEY")
MOTA_MODEL_NAME = os.getenv("MOTA_MODEL_NAME")

# 邮箱配置
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_AUTH_CODE = os.getenv("EMAIL_AUTH_CODE")

# 订阅邮箱存储文件（本地JSON，无需数据库）
SUBSCRIBE_FILE = "subscribers.json"
# 初始化订阅文件（如果不存在则创建）
if not os.path.exists(SUBSCRIBE_FILE):
    with open(SUBSCRIBE_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

# -------------------------- AI摘要功能（魔塔API） --------------------------
def ai_news_summary(news_content):
    """调用魔塔社区AI生成新闻摘要"""
    try:
        # 魔塔API请求头
        headers = {
            "Authorization": f"Bearer {MOTA_API_KEY}",
            "Content-Type": "application/json"
        }
        # AI提示词（针对产品经理新闻优化）
        data = {
            "model": MOTA_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": f"请把以下「人人都是产品经理」的文章内容总结成100字以内的简洁摘要，语言通俗易懂，聚焦产品/互联网核心信息，不要多余废话：\n{news_content}"
                }
            ],
            "temperature": 0.7,  # 摘要稳定性
            "max_tokens": 150     # 限制摘要长度
        }
        # 调用魔塔API
        response = requests.post(MOTA_API_URL, headers=headers, json=data, timeout=15)
        response.raise_for_status()  # 捕获HTTP错误
        result = response.json()
        # 提取AI摘要
        summary = result["choices"][0]["message"]["content"].strip()
        return summary
    except Exception as e:
        print(f"魔塔AI调用失败：{str(e)}")
        # 失败时返回原文前100字
        return news_content[:100] if len(news_content) > 0 else "暂无摘要"

# -------------------------- 新闻抓取功能（人人都是产品经理） --------------------------
def get_news_with_summary():
    """抓取人人都是产品经理的新闻，并生成AI摘要"""
    try:
        # 目标网站地址
        base_url = "https://www.woshipm.com/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        # 抓取首页内容
        response = requests.get(base_url, headers=headers, timeout=10)
        response.encoding = "utf-8"  # 避免中文乱码

        # 正则匹配文章标题和链接（适配页面结构）
        pattern = re.compile(r'<a class="article-title" href="(.*?)" target="_blank">(.*?)</a>')
        matches = pattern.findall(response.text)
        if not matches:
            # 备用正则（防止页面结构小变化）
            pattern = re.compile(r'<a href="(.*?)" class="article-title" target="_blank">(.*?)</a>')
            matches = pattern.findall(response.text)

        # 处理前5条新闻
        summary_news = []
        for link, title in matches[:5]:
            # 补全链接（处理相对路径）
            article_link = link if link.startswith("http") else f"{base_url}{link.lstrip('/')}"
            
            # 抓取文章正文（简化版：只抓标题生成摘要，避免复杂抓取）
            article_content = title  # 零基础简化：直接用标题生成摘要
            
            # 生成AI摘要
            summary = ai_news_summary(article_content)
            
            # 添加到新闻列表
            summary_news.append({
                "title": title,
                "summary": summary,
                "link": article_link
            })
        
        return summary_news if summary_news else [{"title": "今日暂无新闻", "summary": "未抓取到新闻内容", "link": base_url}]
    except Exception as e:
        print(f"新闻抓取失败：{str(e)}")
        return [{"title": "今日暂无新闻", "summary": f"抓取失败：{str(e)[:50]}", "link": "https://www.woshipm.com/"}]

# -------------------------- 邮件发送功能 --------------------------
def send_news_email(to_email, news_list):
    """给指定邮箱发送新闻邮件"""
    try:
        # 构建HTML格式邮件内容
        email_html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <title>每日产品经理新闻摘要</title>
        </head>
        <body>
            <h2>📰 每日产品经理新闻精选</h2>
            <hr>
            <ul style="list-style: none; padding: 0;">
        """
        # 拼接每条新闻
        for news in news_list:
            email_html += f"""
                <li style="margin: 15px 0; padding: 10px; border-bottom: 1px solid #eee;">
                    <h3 style="margin: 0; color: #2c3e50;">{news['title']}</h3>
                    <p style="color: #666; margin: 5px 0;">{news['summary']}</p>
                    <a href="{news['link']}" style="color: #007bff; text-decoration: none;">查看原文 →</a>
                </li>
            """
        email_html += """
            </ul>
            <hr>
            <p style="color: #999; font-size: 12px;">本邮件由AI自动生成，如有问题请忽略</p>
        </body>
        </html>
        """

        # 配置QQ邮箱SMTP
        smtp_server = "smtp.qq.com"
        smtp_port = 465
        # 构建邮件
        msg = MIMEText(email_html, "html", "utf-8")
        msg["From"] = Header(f"每日产品新闻<{EMAIL_SENDER}>", "utf-8")
        msg["To"] = Header(to_email, "utf-8")
        msg["Subject"] = Header("[每日精选] 产品经理新闻摘要", "utf-8")

        # 发送邮件
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(EMAIL_SENDER, EMAIL_AUTH_CODE)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        print(f"邮件发送成功：{to_email}")
        return True
    except Exception as e:
        print(f"邮件发送失败：{to_email} - {str(e)}")
        return False

# -------------------------- 自动发送新闻 --------------------------
def auto_send_daily_news():
    """给所有订阅用户发送每日新闻"""
    # 读取订阅邮箱列表
    with open(SUBSCRIBE_FILE, "r", encoding="utf-8") as f:
        subscribers = json.load(f)
    if not subscribers:
        print("暂无订阅用户，跳过发送")
        return
    
    # 获取带摘要的新闻
    news_list = get_news_with_summary()
    
    # 逐个发送邮件
    for email in subscribers:
        send_news_email(email, news_list)
        time.sleep(1)  # 避免发送过快被限制

# -------------------------- API接口 --------------------------
@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    """用户订阅接口"""
    try:
        # 获取前端传的邮箱
        data = request.get_json()
        email = data.get("email", "").strip()
        
        # 验证邮箱格式
        if not email or "@" not in email:
            return jsonify({"success": False, "msg": "请输入有效的邮箱地址！"}), 400
        
        # 读取现有订阅列表
        with open(SUBSCRIBE_FILE, "r", encoding="utf-8") as f:
            subscribers = json.load(f)
        
        # 检查是否重复订阅
        if email in subscribers:
            return jsonify({"success": True, "msg": "你已订阅成功，无需重复订阅！"}), 200
        
        # 添加新订阅邮箱
        subscribers.append(email)
        with open(SUBSCRIBE_FILE, "w", encoding="utf-8") as f:
            json.dump(subscribers, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True, "msg": "订阅成功！每日将为你发送产品经理新闻摘要～"}), 200
    except Exception as e:
        return jsonify({"success": False, "msg": f"订阅失败：{str(e)[:50]}"}), 500

@app.route("/api/send_news", methods=["GET"])
def manual_send_news():
    """手动触发发送新闻（测试用）"""
    auto_send_daily_news()
    return jsonify({"success": True, "msg": "开始给所有订阅用户发送今日新闻！"})

# -------------------------- 前端页面 --------------------------
@app.route("/")
def index():
    """返回订阅页面"""
    return render_template("index.html")

# -------------------------- 启动服务 --------------------------
if __name__ == "__main__":
    print("服务启动中...访问 http://localhost:5000 即可进入订阅页面")
    print("测试发送新闻：访问 http://localhost:5000/api/send_news")
    app.run(debug=True, port=5000, host="0.0.0.0")
