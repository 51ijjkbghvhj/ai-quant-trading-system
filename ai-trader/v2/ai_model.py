"""AI Model - 通用AI模型接口，兼容OpenAI格式的所有AI提供商"""
import json
import os
import re
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ['NO_PROXY'] = '*'

# ★ 纯动态配置：指向 user_data 目录
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 指向 OH-WorkSpace 根目录
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

API_URL = None
API_KEY = None
MODEL = None
DEBUG_LOG = str(USER_DATA_DIR / "mimo_debug.log")
CONFIG_PATH = str(USER_DATA_DIR / "ai_config.json")

# 支持的AI提供商（OpenAI兼容格式）
SUPPORTED_PROVIDERS = {
    "openai":       {"name": "OpenAI",         "url": "https://api.openai.com/v1/chat/completions",           "models": "gpt-4o, gpt-4o-mini, o1, o3"},
    "deepseek":     {"name": "DeepSeek",        "url": "https://api.deepseek.com/v1/chat/completions",        "models": "deepseek-chat, deepseek-reasoner"},
    "qwen":         {"name": "通义千问",         "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "models": "qwen-max, qwen-plus, qwen-turbo"},
    "doubao":       {"name": "豆包(字节跳动)",  "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "models": "ep-xxx"},
    "hunyuan":      {"name": "腾讯混元",         "url": "https://api.hunyuan.cloud.tencent.com/v1/chat/completions", "models": "hunyuan-turbo, hunyuan-pro"},
    "wenxin":       {"name": "百度文心",         "url": "https://qianfan.baidubce.com/v2/chat/completions",     "models": "ernie-4.0, ernie-3.5"},
    "glm":          {"name": "智谱清言",         "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "models": "glm-4-plus, glm-4-flash"},
    "moonshot":     {"name": "Kimi(月之暗面)",   "url": "https://api.moonshot.cn/v1/chat/completions",         "models": "moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k"},
    "stepfun":      {"name": "阶跃星辰",         "url": "https://api.stepfun.com/v1/chat/completions",         "models": "step-1-8k, step-2-16k"},
    "minimax":      {"name": "MiniMax",          "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",  "models": "abab6.5, abab7"},
    "siliconflow":  {"name": "硅基流动",         "url": "https://api.siliconflow.cn/v1/chat/completions",      "models": "Qwen/Qwen2.5-72B, THUDM/glm-4-9b"},
    "groq":         {"name": "Groq",            "url": "https://api.groq.com/openai/v1/chat/completions",     "models": "llama-3.3-70b, mixtral-8x7b"},
    "together":     {"name": "Together AI",      "url": "https://api.together.xyz/v1/chat/completions",        "models": "meta-llama/Llama-3-70b, Qwen/Qwen2.5-72B"},
    "ollama":       {"name": "Ollama(本地)",     "url": "http://localhost:11434/v1/chat/completions",          "models": "llama3, qwen2.5, deepseek-r1"},
    "lmstudio":     {"name": "LM Studio(本地)",  "url": "http://localhost:1234/v1/chat/completions",           "models": "local-model"},
    "custom":       {"name": "自定义",           "url": "",                                                    "models": ""},
}

def _load_config():
    """从配置文件加载AI配置（纯动态，无保底）"""
    global API_URL, API_KEY, MODEL
    
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"❌ 配置文件不存在: {CONFIG_PATH}")
    
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        
        # 强制要求三个字段都存在
        if not config.get("api_url"): raise ValueError("配置文件缺少 api_url")
        if not config.get("api_key"): raise ValueError("配置文件缺少 api_key")
        if not config.get("model"):  raise ValueError("配置文件缺少 model")
        
        API_URL = config["api_url"]
        API_KEY = config["api_key"]
        MODEL = config["model"]
        
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 JSON 格式错误: {e}")

def reload_config():
    """重新加载配置"""
    _load_config()

# 启动时加载配置
_load_config()

def _debug(msg):
    try:
        from datetime import datetime
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except: pass

def _extract_json(text):
    """从任意文本中提取最外层完整JSON对象
    
    支持：
    - 直接JSON字符串
    - 包含Markdown代码块的JSON
    - JSON前后有自然语言
    - 嵌套JSON对象
    """
    if not text or not isinstance(text, str):
        return None
    
    # 清除Markdown代码块标记
    if '```' in text:
        matches = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if matches:
            text = matches[0]
    
    # 查找第一个{
    start = text.find('{')
    if start == -1:
        return None
    
    # 使用栈平衡匹配完整JSON对象
    depth = 0
    in_string = False
    escape_next = False
    end = -1
    
    for i in range(start, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    
    if end != -1:
        return text[start:end+1]
    
    return None

def call_mimo(prompt, system_prompt="", max_tokens=16000, temperature=0.3, json_mode=False):
    """调用AI模型（通用OpenAI兼容格式）
    
    ★ 全模型适配器：智能处理所有模型响应格式
    - OpenAI (gpt-4o, o1, o3)
    - DeepSeek (deepseek-chat, deepseek-reasoner, v4-pro)
    - 通义千问 (qwen-max, qwen-plus)
    - Kimi (moonshot-v1)
    - 智谱 (glm-4)
    - 豆包、文心、混元、MiniMax等
    - Ollama/LM Studio本地部署
    
    json_mode=True 时：
    - 自动从任何字段提取JSON
    - 支持推理模型(reasoning_content)
    - 返回纯JSON字符串，不含自然语言
    """
    global API_URL, API_KEY, MODEL
    _load_config()
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    
    if "reasoner" in MODEL.lower() or "r1" in MODEL.lower() or "thinking" in MODEL.lower():
        body["max_tokens"] = max_tokens

    try:
        final_url = API_URL
        if not final_url.endswith('/chat/completions'):
            if final_url.endswith('/v1'):
                final_url += '/chat/completions'
            elif final_url.endswith('/'):
                final_url += 'chat/completions'
            else:
                final_url += '/chat/completions'
        
        _debug(f"Calling {MODEL}...")
        _debug(f"URL: {final_url[:60]}...")
        resp = requests.post(
            final_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            json=body,
            timeout=120,
            verify=False,
            proxies=None,
        )

        _debug(f"Response status: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            _debug(f"Response body: {json.dumps(result, ensure_ascii=False)[:500]}")
            
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                msg = choice.get("message", {})
                
                # ★ 全模型内容提取引擎
                # 收集所有可能的文本源（按优先级排序）
                sources = [
                    ("message.content", msg.get("content", "")),
                    ("message.reasoning_content", msg.get("reasoning_content", "")),
                    ("choice.content", choice.get("content", "")),
                    ("choice.text", choice.get("text", "")),
                    ("delta.content", choice.get("delta", {}).get("content", "")),
                    ("delta.reasoning_content", choice.get("delta", {}).get("reasoning_content", "")),
                ]
                
                # JSON模式：智能提取
                if json_mode:
                    # 策略1：检查每个源是否包含JSON
                    for src_name, src_text in sources:
                        if not src_text or len(src_text.strip()) < 10:
                            continue
                        
                        json_str = _extract_json(src_text)
                        if json_str:
                            _debug(f"JSON mode: extracted JSON from {src_name} ({len(json_str)} chars)")
                            return json_str
                    
                    # 策略2：如果单个源没有，尝试合并所有非空源
                    combined = "\n".join([text for _, text in sources if text and len(text.strip()) > 10])
                    if combined:
                        json_str = _extract_json(combined)
                        if json_str:
                            _debug(f"JSON mode: extracted JSON from combined sources ({len(json_str)} chars)")
                            return json_str
                    
                    # 没有找到JSON
                    _debug(f"JSON mode: no JSON found in any source")
                    return ""
                
                # 非JSON模式：返回优先级最高的内容
                for src_name, src_text in sources:
                    if src_text and src_text.strip():
                        _debug(f"Content from {src_name} ({len(src_text)} chars): {src_text[:200]}")
                        return src_text
                
                # 所有源都为空
                _debug(f"No content in any source")
                return ""
            
            return json.dumps(result, ensure_ascii=False)
        else:
            _debug(f"HTTP Error: {resp.status_code} {resp.text[:200]}")
            return f"[{MODEL}] HTTP {resp.status_code}: {resp.text[:200]}"

    except requests.exceptions.Timeout:
        _debug(f"Timeout after 120s")
        return f"[{MODEL}] 请求超时(120s)，请检查网络或API状态"
    except requests.exceptions.ConnectionError as e:
        _debug(f"Connection error: {e}")
        return f"[{MODEL}] 连接失败，请检查API地址是否正确"
    except Exception as e:
        _debug(f"Exception: {type(e).__name__}: {str(e)[:200]}")
        return f"[{MODEL}] {type(e).__name__}: {str(e)[:150]}"


def test_connection(override_url=None, override_key=None):
    """测试AI连接（通过获取模型列表验证）"""
    global API_URL, API_KEY, MODEL
    _load_config()
    
    test_url = override_url or API_URL
    test_key = override_key or API_KEY
    old_api_url, old_api_key = API_URL, API_KEY
    API_URL, API_KEY = test_url, test_key
    
    try:
        ok, models = list_models(test_url, test_key)
        if ok and len(models) > 0:
            return True, {
                "connected": True,
                "model": models[0] if models else MODEL,
                "api_url": test_url,
                "response": "Connection OK via /models",
                "available_models": models
            }
        
        result = call_mimo("Reply: OK", max_tokens=10)
        connected = "Error" not in result and "HTTP" not in result
        return connected, {
            "connected": connected,
            "model": MODEL,
            "api_url": test_url,
            "response": result[:200] if result else ""
        }
    finally:
        API_URL, API_KEY = old_api_url, old_api_key

def get_provider_info():
    """获取支持的AI提供商列表"""
    return SUPPORTED_PROVIDERS

def list_models(api_url, api_key):
    """获取可用模型列表（支持OpenAI兼容格式和中转站）"""
    try:
        clean_url = api_url.rstrip('/')
        if '/chat/completions' in clean_url:
            models_url = clean_url.replace('/chat/completions', '/models')
        elif '/v1' in clean_url:
            models_url = clean_url + '/models'
        else:
            models_url = clean_url + '/v1/models'

        resp = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=15, verify=False, proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data:
                models = [m.get("id", str(m)) for m in data["data"] if isinstance(m, dict)]
                return True, sorted(models)
            elif "models" in data:
                return True, data["models"]
            elif isinstance(data, list):
                return True, [m.get("id", str(m)) for m in data]
        
        chat_url = clean_url
        if not clean_url.endswith('/chat/completions'):
            if '/v1' in clean_url:
                chat_url = clean_url + '/chat/completions'
            else:
                chat_url = clean_url + '/v1/chat/completions'

        test_resp = requests.post(
            chat_url, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={"model": "__test__", "messages": [{"role": "user", "content": "test"}], "max_tokens": 5},
            timeout=10, verify=False, proxies={"http": None, "https": None}
        )
        if test_resp.status_code == 404 or test_resp.status_code == 400:
            err_text = test_resp.text.lower()
            match = re.search(r'\[([^\]]+)\]', err_text)
            if match:
                models = [m.strip().strip('"') for m in match.group(1).split(',') if m.strip()]
                if models: return True, models
        
        return False, [f"获取失败 (Status: {resp.status_code}). 请检查 URL 格式 (建议以 /v1 结尾) 和 API Key"]
            
    except requests.exceptions.Timeout:
        return False, ["连接超时，请检查网络"]
    except requests.exceptions.ConnectionError:
        return False, ["无法连接服务器"]
    except Exception as e:
        return False, [str(e)]
