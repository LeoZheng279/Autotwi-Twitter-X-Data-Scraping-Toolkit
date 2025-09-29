# 安装必要的库: pip install selenium beautifulsoup4 pandas
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# --- 全局设置 ---
# 【新功能】自动化任务的配置文件名
TASKS_FILE = 'tasks.txt'

# 其他设置
COOKIES_FILE = 'x_cookies.json'
MAX_WORKERS = 2
HEADLESS_MODE = True
REPLY_RETWEET_LIMIT = 20
SEARCH_LIMIT = 120 # 对每个任务，搜索120条推文链接
MIN_RETWEETS = 0  # 对每个任务，搜索的最小转推量
MIN_FAVES = 10 # 对每个任务，搜索的最小点赞量

# 【新增】当发生严重错误时，脚本暂停的秒数
PAUSE_ON_ERROR_SECONDS = 241 

def save_cookies(driver, file_path):
    """保存当前浏览器的Cookies到文件"""
    with open(file_path, 'w') as f:
        json.dump(driver.get_cookies(), f)
    print(f"Cookies have been saved to {file_path}")

def load_cookies(driver, file_path):
    """从文件加载Cookies到浏览器"""
    if os.path.exists(file_path):
        driver.get("https://x.com/")
        with open(file_path, 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        return True
    return False

def parse_tweet_article(article_soup):
    """从一个包含单条推文的 'article' HTML片段中解析出所有数据"""
    try:
        time_element = article_soup.find('time')
        if not time_element or not time_element.find_parent('a'): return None
        post_link = "https://x.com" + time_element.find_parent('a')['href']
        post_time = time_element['datetime']
        user_id = post_link.split('/')[3]
        user_name_div = article_soup.find('div', {'data-testid': 'User-Name'})
        nickname = user_name_div.find_all('span')[0].text if user_name_div else user_id
        tweet_text_div = article_soup.find('div', {'data-testid': 'tweetText'})
        if tweet_text_div:
            for img in tweet_text_div.find_all('img', alt=True): img.replace_with(img['alt'])
        content = tweet_text_div.get_text(separator='\n', strip=True) if tweet_text_div else ''
        emoji_pattern = re.compile("[" u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF" u"\U0001F680-\U0001F6FF" u"\U0001F1E0-\U0001F1FF" u"\U00002702-\U000027B0" u"\U000024C2-\U0001F251" "]+", flags=re.UNICODE)
        emojis = emoji_pattern.findall(content)
        hashtags = [tag.text for tag in article_soup.find_all('a', href=re.compile(r'/hashtag/'))]
        reply_count_element = article_soup.find('button', {'data-testid': 'reply'}) or article_soup.find('div', {'data-testid': 'reply'})
        retweet_count_element = article_soup.find('button', {'data-testid': 'retweet'}) or article_soup.find('div', {'data-testid': 'retweet'})
        like_count_element = article_soup.find('button', {'data-testid': 'like'}) or article_soup.find('div', {'data-testid': 'like'})

        def parse_metric(element):
            if not element: return 0
            aria_label = element.get('aria-label', '')
            if aria_label:
                match = re.search(r'([\d,]+)', aria_label)
                if match:
                    try: return int(match.group(1).replace(',', ''))
                    except (ValueError, TypeError): pass
            text = element.get_text(strip=True).upper()
            if not text: return 0
            if 'K' in text: return int(float(text.replace('K', '')) * 1000)
            if 'M' in text: return int(float(text.replace('M', '')) * 1000000)
            try: return int(text)
            except (ValueError, TypeError): return 0

        return {"nickname": nickname, "user_id": user_id, "platform": "X", "post_time": post_time, "ip_location": "N/A (Not available on web version)", "hashtags": ", ".join(hashtags), "post_text": content, "emojis": emojis, "reply_count": parse_metric(reply_count_element), "retweet_count": parse_metric(retweet_count_element), "like_count": parse_metric(like_count_element), "post_url": post_link}
    except Exception: return None

def scroll_and_collect(driver, seen_tweets, max_scrolls=1):
    """通过限制滚动次数来快速采集样本"""
    collected_data = []
    scroll_count = 0
    while scroll_count < max_scrolls:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('article', {'data-testid': 'tweet'})
        new_tweets_found = False
        for article in articles:
            parsed_data = parse_tweet_article(article)
            if parsed_data and parsed_data['post_url'] not in seen_tweets:
                collected_data.append(parsed_data)
                seen_tweets.add(parsed_data['post_url'])
                new_tweets_found = True
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2.0, 3.5))
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        scroll_count += 1
        if new_height == last_height and not new_tweets_found:
            break
            
    return collected_data

def get_chrome_options():
    """配置Chrome浏览器选项以提高速度"""
    options = webdriver.ChromeOptions()
    if HEADLESS_MODE: options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    return options

def perform_initial_login():
    """仅在没有cookies时执行，用于首次手动登录"""
    if os.path.exists(COOKIES_FILE): return
    print("Cookies file not found. A browser will open for you to log in.")
    print("Please log in manually. You have 120 seconds...")
    login_options = get_chrome_options()
    if any('--headless' in arg for arg in login_options.arguments): login_options.arguments.remove('--headless')
    driver = webdriver.Chrome(options=login_options)
    driver.get("https://x.com/login")
    try:
        WebDriverWait(driver, 120).until(EC.url_contains("home"))
        print("Login successful! Saving cookies for future use...")
        save_cookies(driver, COOKIES_FILE)
    except Exception: print("Login timed out or failed.")
    finally: driver.quit()

def search_for_popular_tweets(driver, keyword, start_date, end_date, min_retweets, limit):
    """根据关键词、日期范围和最小转发量搜索推文链接"""
    print(f"开始搜索关键词 '{keyword}' 从 {start_date} 到 {end_date} (最小转发量: {min_retweets}) 的推文...")
    search_query = f"{keyword} min_retweets:{min_retweets} since:{start_date} until:{end_date}"
    search_url = f"https://x.com/search?q={search_query}&src=typed_query"
    driver.get(search_url)
    
    tweet_urls = set()
    retries = 5
    while len(tweet_urls) < limit and retries > 0:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('article', {'data-testid': 'tweet'})
        
        if not articles:
            time.sleep(2)
            retries -= 1
            continue

        for article in articles:
            time_element = article.find('time')
            if time_element and time_element.find_parent('a'):
                post_link = "https://x.com" + time_element.find_parent('a')['href']
                tweet_urls.add(post_link)
                if len(tweet_urls) >= limit:
                    break
        
        print(f"  [搜索进度] 已找到 {len(tweet_urls)} / {limit} 个链接...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2.5, 4.0))
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            retries -= 1
            print(f"  [搜索提示] 似乎已到达搜索结果底部，剩余尝试次数: {retries}")
    
    print(f"搜索完成，共找到 {len(tweet_urls)} 个唯一链接。")
    return list(tweet_urls)

def process_url(url, output_dir):
    """处理单个URL的完整爬取流程"""
    thread_id = f"线程-{random.randint(100, 999)}"
    print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 开始处理链接: {url}")
    driver = webdriver.Chrome(options=get_chrome_options())
    try:
        if not load_cookies(driver, COOKIES_FILE):
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 无法加载Cookies，跳过链接 {url}")
            return

        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
        time.sleep(random.uniform(2, 3))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('article', {'data-testid': 'tweet'})
        
        source_tweet = None
        for article in articles:
            parsed_data = parse_tweet_article(article)
            if parsed_data and url.endswith(parsed_data['post_url'].replace("https://x.com", "")):
                source_tweet = parsed_data
                break
        
        if not source_tweet:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [失败] 页面加载后未能找到并解析源帖子 {url}")
            return

        seen_tweets = {source_tweet['post_url']}

        final_replies = scroll_and_collect(driver, seen_tweets, max_scrolls=4)
        quotes_url = url.rstrip('/') + "/quotes"
        all_retweets = []
        try:
            driver.get(quotes_url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
            all_retweets = scroll_and_collect(driver, seen_tweets, max_scrolls=4)
        except Exception: pass

        if len(final_replies) > REPLY_RETWEET_LIMIT: sampled_replies = random.sample(final_replies, REPLY_RETWEET_LIMIT)
        else: sampled_replies = final_replies

        if len(all_retweets) > REPLY_RETWEET_LIMIT: sampled_retweets = random.sample(all_retweets, REPLY_RETWEET_LIMIT)
        else: sampled_retweets = all_retweets

        source_tweet['replies'] = sampled_replies
        source_tweet['retweets_with_comment'] = sampled_retweets
        
        post_time_str = source_tweet.get('post_time', str(time.time()))
        filename_time = post_time_str.replace('T', '_').replace(':', '-').split('.')[0]
        tweet_id = url.split('/')[-1]
        output_filename = f"{filename_time}_id_{tweet_id}.json"
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(source_tweet, f, ensure_ascii=False, indent=4)
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [成功] {url} 的数据已保存至 {output_path}")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 处理链接 {url} 时发生严重错误: {e}")
        wait_time = 180
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 遇到严重错误，程序将暂停 {wait_time // 60} 分钟后继续处理其他链接...")
        for i in range(wait_time, 0, -1):
            print(f"\r[{time.strftime('%H:%M:%S')}] {thread_id}: 倒计时: {i:03d} 秒...", end="", flush=True)
            time.sleep(1)
        print(f"\n[{time.strftime('%H:%M:%S')}] {thread_id}: 暂停结束，此线程将退出。")
    finally:
        driver.quit()

def process_url_sequentially(driver, url, output_dir):
    """
    【再次重构】处理单个URL的爬取流程。
    增加了在遇到严重错误时自动暂停的功能。
    """
    thread_id = f"浏览器实例"
    print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 开始处理链接: {url}")
    try:
        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
        time.sleep(random.uniform(2, 3))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('article', {'data-testid': 'tweet'})
        
        source_tweet = None
        for article in articles:
            parsed_data = parse_tweet_article(article)
            if parsed_data and url.endswith(parsed_data['post_url'].replace("https://x.com", "")):
                source_tweet = parsed_data
                break
        
        if not source_tweet:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [失败] 页面加载后未能找到并解析源帖子 {url}")
            return

        seen_tweets = {source_tweet['post_url']}

        final_replies = scroll_and_collect(driver, seen_tweets, max_scrolls=3)
        quotes_url = url.rstrip('/') + "/quotes"
        all_retweets = []
        try:
            driver.get(quotes_url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']")))
            all_retweets = scroll_and_collect(driver, seen_tweets, max_scrolls=3)
        except Exception:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 访问或解析引用推文页面失败: {quotes_url}")
            pass

        if len(final_replies) > REPLY_RETWEET_LIMIT: sampled_replies = random.sample(final_replies, REPLY_RETWEET_LIMIT)
        else: sampled_replies = final_replies

        if len(all_retweets) > REPLY_RETWEET_LIMIT: sampled_retweets = random.sample(all_retweets, REPLY_RETWEET_LIMIT)
        else: sampled_retweets = all_retweets

        source_tweet['replies'] = sampled_replies
        source_tweet['retweets_with_comment'] = sampled_retweets
        
        post_time_str = source_tweet.get('post_time', str(time.time()))
        filename_time = post_time_str.replace('T', '_').replace(':', '-').split('.')[0]
        tweet_id = url.split('/')[-1]
        output_filename = f"{filename_time}_id_{tweet_id}.json"
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(source_tweet, f, ensure_ascii=False, indent=4)
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: [成功] {url} 的数据已保存至 {output_path}")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 处理链接 {url} 时发生严重错误: {e}")
        
        # --- 【核心修改】在这里重新加入暂停逻辑 ---
        wait_time = PAUSE_ON_ERROR_SECONDS
        if wait_time > 0:
            print(f"[{time.strftime('%H:%M:%S')}] {thread_id}: 遇到严重错误，程序将暂停 {wait_time // 60} 分钟 ({wait_time} 秒) 以应对反爬机制...")
            for i in range(wait_time, 0, -1):
                print(f"\r[{time.strftime('%H:%M:%S')}] {thread_id}: 倒计时: {i:03d} 秒...", end="", flush=True)
                time.sleep(1)
            print(f"\n[{time.strftime('%H:%M:%S')}] {thread_id}: 暂停结束，将继续处理下一个链接。")
        # ------------------------------------------

def main():
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            tasks = [line.strip().split(',') for line in f if line.strip() and not line.startswith('#')]
        if not tasks:
            print(f"{TASKS_FILE} 为空或格式不正确。")
            return
    except FileNotFoundError:
        print(f"未找到任务配置文件 '{TASKS_FILE}'。")
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            f.write("# 格式: 搜索关键词,开始日期(YYYY-MM-DD),结束日期(YYYY-MM-DD),保存文件夹名称\n")
            f.write("Trump,2024-05-01,2024-05-02,Trump_May_2024\n")
            f.write("Biden,2024-05-01,2024-05-02,Biden_May_2024\n")
        print(f"已为您创建一个示例 '{TASKS_FILE}' 文件。")
        return

    perform_initial_login()

    # --- 【重构核心】在所有任务开始前，只初始化一次浏览器 ---
    driver = None
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        if not load_cookies(driver, COOKIES_FILE):
            print("无法加载Cookies，程序无法继续执行。")
            return

        # --- 按顺序执行每个任务 ---
        for task_index, task in enumerate(tasks):
            if len(task) != 4:
                print(f"任务 {task_index+1} 格式错误，已跳过: {task}")
                continue
            
            keyword, start_date, end_date, output_dir = [t.strip() for t in task]
            print(f"\n{'='*50}")
            print(f"开始执行任务 {task_index+1}/{len(tasks)}: 关键词='{keyword}', 日期='{start_date}' to '{end_date}', 文件夹='{output_dir}'")
            print(f"{'='*50}\n")

            os.makedirs(output_dir, exist_ok=True)
            url_list_file = os.path.join(output_dir, 'urls_to_process.json')

            # --- 搜索或加载URL列表（这部分逻辑不变，但使用同一个driver）---
            target_urls = []
            if os.path.exists(url_list_file):
                print(f"找到任务 '{keyword}' 的链接列表文件，将从中加载链接。")
                with open(url_list_file, 'r') as f:
                    target_urls = json.load(f)
            else:
                print("未找到此任务的链接列表文件，将执行新的搜索...")
                # 注意：这里复用了主driver，而不是创建一个新的
                target_urls = search_for_popular_tweets(driver, keyword, start_date, end_date, MIN_RETWEETS, SEARCH_LIMIT)
                
                if target_urls:
                    with open(url_list_file, 'w') as f:
                        json.dump(target_urls, f, indent=4)
                    print(f"已将 {len(target_urls)} 个搜索到的链接保存至 '{url_list_file}'")

            if not target_urls:
                print(f"任务 '{keyword}' 未能获取任何推文链接，跳过此任务。")
                continue
                
            # --- 检查已完成的任务 ---
            processed_ids = set()
            for filename in os.listdir(output_dir):
                match = re.search(r'_id_(\d+).json$', filename)
                if match:
                    processed_ids.add(match.group(1))
            
            pending_urls = [url for url in target_urls if url.split('/')[-1] not in processed_ids]
            
            if not pending_urls:
                print(f"任务 '{keyword}' 的所有链接均已处理完毕！")
                continue

            print(f"\n任务 '{keyword}': 总链接数: {len(target_urls)} | 已完成: {len(processed_ids)} | 待处理: {len(pending_urls)}")
            
            # --- 【重构核心】使用简单的for循环顺序处理，代替线程池 ---
            processed_count = 0
            total_pending = len(pending_urls)
            for url in pending_urls:
                # 调用重构后的函数，传入共享的driver实例
                process_url_sequentially(driver, url, output_dir)
                processed_count += 1
                print(f"\n--- 任务 '{keyword}' 进度: {processed_count}/{total_pending} 个待办链接已处理完毕 ---\n")

        print("\n所有任务均已处理完毕。")

    except Exception as e:
        print(f"程序在执行过程中遇到未处理的严重错误: {e}")
    finally:
        # --- 【重构核心】在程序完全结束时，关闭浏览器 ---
        if driver:
            print("所有任务完成，正在关闭浏览器...")
            driver.quit()

if __name__ == "__main__":
    main()
