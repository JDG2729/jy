import requests
import os
from urllib.parse import urlparse

def download_image(image_url, save_path, timeout=15):
    """
    下载指定的HTTPS图片（适配yyys365.top域名）
    
    Args:
        image_url (str): 图片的HTTPS链接
        save_path (str): 图片保存的完整路径
        timeout (int): 请求超时时间，默认15秒
    
    Returns:
        bool: 下载成功返回True，失败返回False
    """
    if not image_url or not image_url.startswith(('http://', 'https://')):
        print(f"错误：无效的图片URL: {image_url}")
        return False
    
    # 创建保存目录
    save_dir = os.path.dirname(save_path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
    
    # 适配目标网站的请求头（关键）
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8',
        'Referer': 'https://yyys365.top/',  # 必须匹配目标网站域名
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    
    try:
        # 针对该网站的特殊配置
        response = requests.get(
            image_url,
            headers=headers,
            timeout=timeout,
            verify=False,
            stream=True,
            allow_redirects=True  # 允许重定向
        )
        
        response.raise_for_status()
        
        # 写入文件
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"✅ 图片下载成功！保存路径：{save_path}")
        return True
    
    except Exception as e:
        print(f"❌ 下载失败：{str(e)}")
        return False

# ------------------- 测试下载指定链接 -------------------
if __name__ == "__main__":
    # 你的目标图片链接
    target_url = "https://yyys365.top/static/card_name/dongfanghong/E00206726.png"
    # 保存路径（可自行修改）
    save_path = "./downloads/E00206726.png"
    
    # 执行下载
    download_image(target_url, save_path)