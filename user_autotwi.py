# -*- coding: utf-8 -*-
# 安装必要的库: pip install selenium beautifulsoup4
import time
import random
import json
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# --- 全局设置 ---
USERS_FILE = 'users.txt'  # 包含用户ID的输入文件名
COOKIES_FILE = 'x_cookies.json'  # 登录凭证文件名
OUTPUT_DIR = 'scraped_users'  # 结果保存目录
HEADLESS_MODE = True  # True为无头模式（不显示浏览器），False为显示浏览器
MAX_TWEETS = 10  # 每个用户爬取的近期帖子数量

# --- 辅助函数 ---

def save_cookies(driver, file_path):
    """保存当前浏览器的Cookies到文件"""
    with open(file_path, 'w') as f:
        json.dump(driver.get_cookies(), f)
    print(f"Cookies 已保存至 {file_path}")

def load_cookies(driver, file_path):
    """从文件加载Cookies到浏览器"""
    if os.path.exists(file_path):
        driver.get("https://x.com/")
        time.sleep(1)
        with open(file_path, 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                del cookie['sameSite']
            driver.add_cookie(cookie)
        print("Cookies 加载成功。")
        return True
    print("未找到 Cookies 文件。")
    return False

def get_chrome_options():
    """配置Chrome浏览器选项"""
    options = webdriver.ChromeOptions()
    if HEADLESS_MODE:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    return options

def perform_initial_login():
    """仅在没有cookies时执行，用于首次手动登录"""
    if os.path.exists(COOKIES_FILE):
        return
    print("未找到Cookies文件，将打开浏览器以便您手动登录。")
    print("请在120秒内完成登录...")
    login_options = get_chrome_options()
    if any('--headless' in arg for arg in login_options.arguments):
        login_options.arguments.remove('--headless')
    driver = webdriver.Chrome(options=login_options)
    driver.get("https://x.com/login")
    try:
        WebDriverWait(driver, 120).until(EC.url_contains("home"))
        print("登录成功！正在保存Cookies以备后用...")
        save_cookies(driver, COOKIES_FILE)
    except Exception as e:
        print(f"登录超时或失败: {e}")
    finally:
        driver.quit()

def parse_metric(element):
    """从互动数据元素中更准确地解析出数字"""
    if not element:
        return 0
    aria_label = element.get('aria-label', '')
    if aria_label:
        match = re.search(r'([\d,]+)', aria_label)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except (ValueError, TypeError):
                pass
    return parse_count_text(element.get_text(strip=True))

def parse_count_text(text):
    """【修复】解析带单位（万, K, M）的数字文本"""
    if not text:
        return 0
    text = text.replace(',', '').strip().upper()
    try:
        if '万' in text:
            num = float(text.replace('万', ''))
            return int(num * 10000)
        if 'K' in text:
            num = float(text.replace('K', ''))
            return int(num * 1000)
        if 'M' in text:
            num = float(text.replace('M', ''))
            return int(num * 1000000)
        return int(text)
    except (ValueError, TypeError):
        return 0

def parse_tweet_article(article_soup):
    """从一个包含单条推文的 'article' HTML片段中解析出关键数据。"""
    try:
        time_element = article_soup.find('time')
        if not time_element or not time_element.find_parent('a'):
            return None
        post_link = "https://x.com" + time_element.find_parent('a')['href']
        post_time = time_element['datetime']
        tweet_text_div = article_soup.find('div', {'data-testid': 'tweetText'})
        content = tweet_text_div.get_text(separator='\n', strip=True) if tweet_text_div else ''
        reply_element = article_soup.find('button', {'data-testid': 'reply'}) or article_soup.find('div', {'data-testid': 'reply'})
        retweet_element = article_soup.find('button', {'data-testid': 'retweet'}) or article_soup.find('div', {'data-testid': 'retweet'})
        like_element = article_soup.find('button', {'data-testid': 'like'}) or article_soup.find('div', {'data-testid': 'like'})
        reply_count = parse_metric(reply_element)
        retweet_count = parse_metric(retweet_element)
        like_count = parse_metric(like_element)
        return {"post_time": post_time, "post_text": content, "reply_count": reply_count, "retweet_count": retweet_count, "like_count": like_count, "post_url": post_link}
    except Exception:
        return None

# --- 核心功能函数 ---

def scrape_user_profile(driver, user_id):
    """爬取单个用户的个人主页信息。"""
    url = f"https://x.com/{user_id}"
    print(f"\n正在处理用户: {user_id} ({url})")
    try:
        driver.get(url)
        # 等待页面核心部分（用户名）加载
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="UserName"]'))
        )
        time.sleep(random.uniform(2, 4)) # 等待页面稳定
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        user_data = {"scraped_url": url, "scraped_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        
        username_element = soup.select_one('div[data-testid="UserName"] span > span')
        user_data['username'] = username_element.text.strip() if username_element else "N/A"
        userid_element = soup.select_one('div[data-testid="UserScreenName"] span')
        user_data['user_id'] = userid_element.text.strip() if userid_element else f"@{user_id}"
        bio_element = soup.select_one('div[data-testid="UserDescription"]')
        user_data['bio'] = bio_element.get_text(separator='\n', strip=True) if bio_element else ""
        location_element = soup.select_one('span[data-testid="UserLocation"] span')
        user_data['location'] = location_element.text.strip() if location_element else "N/A"
        website_element = soup.select_one('a[data-testid="UserUrl"] span')
        user_data['website'] = website_element.text.strip() if website_element else "N/A"
        join_date_element = soup.select_one('span[data-testid="UserJoinDate"] span')
        user_data['join_date'] = join_date_element.text.strip() if join_date_element else "N/A"
        
        # --- 【修复】采用更精确的选择器来提取关注和粉丝数 ---
        following_count = 0
        followers_count = 0
        
        # 直接通过href属性的后缀来定位元素，更精确
        following_link = soup.select_one(f'a[href$="/following"]')
        if following_link:
            # 寻找所有可能包含数字的span元素
            count_elements = following_link.select('span')
            for span in count_elements:
                text = span.get_text(strip=True)
                if text and any(char.isdigit() or char in '万KM.' for char in text):
                    following_count = parse_count_text(text)
                    break
                
        # followers链接可能以 /followers 或 /verified_followers 结尾
        followers_link = soup.select_one(f'a[href$="/verified_followers"]') or soup.select_one(f'a[href$="/followers"]')
        if followers_link:
            # 寻找所有可能包含数字的span元素
            count_elements = followers_link.select('span')
            for span in count_elements:
                text = span.get_text(strip=True)
                if text and any(char.isdigit() or char in '万KM.' for char in text):
                    followers_count = parse_count_text(text)
                    break
        
        user_data['following_count'] = following_count
        user_data['followers_count'] = followers_count
        user_data['ip_location'] = "N/A (无法从公开页面获取)"

        print(f"正在为 {user_id} 爬取最近 {MAX_TWEETS} 条帖子...")
        # --- 【修复】增加多次滚动逻辑以加载更多帖子 ---
        scroll_attempts = 0
        last_height = driver.execute_script("return document.body.scrollHeight")
        while scroll_attempts < 3: # 最多滚动3次来加载帖子
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2, 3))
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break # 如果页面高度不变，说明已到底部
            last_height = new_height
            scroll_attempts += 1
        
        # 滚动后重新解析页面，获取所有已加载的帖子
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        tweet_articles = soup.find_all('article', {'data-testid': 'tweet'}, limit=MAX_TWEETS)
        
        recent_tweets = []
        for article in tweet_articles:
            parsed_tweet = parse_tweet_article(article)
            if parsed_tweet:
                recent_tweets.append(parsed_tweet)
        
        user_data['recent_tweets'] = recent_tweets
        
        output_filename = f"{user_id}.json"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
        print(f"[成功] 用户 {user_id} 的数据已保存至 {output_path}")

    except Exception as e:
        print(f"[失败] 处理用户 {user_id} 时发生错误: {e}")
        error_info = {"user_id": user_id, "error_message": str(e), "error_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        output_filename = f"{user_id}_error.json"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(error_info, f, ensure_ascii=False, indent=4)

def main():
    """主执行函数"""
    if not os.path.exists(USERS_FILE):
        print(f"未找到用户列表文件 '{USERS_FILE}'。")
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            f.write("# 请在此文件中输入用户ID，每行一个\n")
            f.write("WhiteHouse\n")
            f.write("nasa\n")
            f.write("google\n")
        print(f"已为您创建一个示例 '{USERS_FILE}' 文件。请根据需要修改后重新运行。")
        return

    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        user_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not user_ids:
        print(f"'{USERS_FILE}' 文件为空或不包含有效用户ID。")
        return

    perform_initial_login()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    driver = None
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        if not load_cookies(driver, COOKIES_FILE):
            print("无法加载Cookies，程序无法继续执行。请检查或删除 x_cookies.json 文件后重试。")
            return
        
        print(f"\n准备就绪，将处理 {len(user_ids)} 个用户...")
        
        for user_id in user_ids:
            scrape_user_profile(driver, user_id)
            sleep_time = random.uniform(5, 12)
            print(f"暂停 {sleep_time:.1f} 秒...")
            time.sleep(sleep_time)

        print("\n所有用户处理完毕！")

    except Exception as e:
        print(f"程序在执行过程中遇到未处理的严重错误: {e}")
    finally:
        if driver:
            print("正在关闭浏览器...")
            driver.quit()

if __name__ == "__main__":
    main()

