"""
News Pipeline - 新闻打标系统
职责：为新闻增加结构化标签（类型/影响力/资金关联度）。
原则：不过滤、不删除，只提供结构化视角。
"""

def tag_news(news_list):
    """
    给新闻列表打标签。
    返回: 带有 tags 字段的 news 列表。
    """
    tagged_news = []
    
    # 关键词词典
    keywords = {
        "policy": ["发改委", "央行", "证监会", "国务院", "发布", "意见", "规划", "支持", "补贴"],
        "rumor": ["传闻", "据说", "或", "拟", "有望", "网传"],
        "earnings": ["业绩", "净利", "财报", "预增", "预减", "分红", "高送转"],
        "market": ["资金", "北向", "主力", "流入", "流出", "涨停", "跌停", "龙虎榜"],
        "event": ["复牌", "停牌", "减持", "增持", "中标", "合作", "重组"],
    }
    
    # 资金关联度词典
    capital_keywords = ["涨停", "突破", "新高", "放量", "资金", "主力", "北向"]

    for item in news_list:
        title = (item.get("title", "") or "") + " " + (item.get("digest", "") or "")
        tags = {"type": "other", "impact_score": 30, "capital_relevance": 0.0}
        
        # 1. 识别类型
        for t, words in keywords.items():
            if any(w in title for w in words):
                tags["type"] = t
                break
        
        # 2. 评估影响力 (Impact Score)
        if "涨停" in title or "新高" in title:
            tags["impact_score"] = 90
        elif any(w in title for w in ["央行", "发改委", "国务院"]):
            tags["impact_score"] = 85
        elif "传闻" in title:
            tags["impact_score"] = 70 # 传闻虽然真假未知，但短期影响力大
        elif "减持" in title:
            tags["impact_score"] = 60
        else:
            tags["impact_score"] = 40
            
        # 3. 资金关联度 (Capital Relevance)
        # 只有直接影响买卖盘的信息才算高关联
        if any(w in title for w in capital_keywords):
            tags["capital_relevance"] = 0.9
        elif tags["type"] in ["policy", "earnings"]:
            tags["capital_relevance"] = 0.7
        else:
            tags["capital_relevance"] = 0.3
            
        # 将 tags 合并回 item
        item["tags"] = tags
        tagged_news.append(item)
        
    return tagged_news

def format_news_for_ai(news_list):
    """
    将打标后的新闻格式化为 AI 可读取的紧凑文本。
    """
    lines = []
    # 按资本关联度排序，高关联在前
    sorted_news = sorted(news_list, key=lambda x: x.get("tags", {}).get("capital_relevance", 0), reverse=True)
    
    for item in sorted_news[:10]: # 只取 Top 10
        t = item.get("tags", {})
        title = item.get("title", "")
        # 格式: [类型][影响:分][资金:高/中/低] 标题
        cap_level = "高" if t.get("capital_relevance", 0) > 0.7 else "中" if t.get("capital_relevance", 0) > 0.4 else "低"
        line = f"[{t.get('type','?')}] [影响:{t.get('impact_score',0)}] [资金:{cap_level}] {title}"
        lines.append(line)
        
    return "\n".join(lines)
