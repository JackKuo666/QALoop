"""
Wiki 问答对生成工具 - 测试版本
直接使用样本数据进行测试
"""
import json
import os
import re
import time
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ==== API 配置 ====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("请在.env文件中设置OPENAI_API_KEY")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

DEFAULT_MODEL = "gpt-5.1"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8000

# ==== 数据配置 ====
SAMPLE_DATA_DIR = "examples/sample_data_v2"
OUTPUT_FILE = "examples/output_v2_test.jsonl"

# ==== QA 生成 Prompt ====
QA_GENERATION_PROMPT = """# 角色定位

你是一个农业领域专家，通晓农业领域基础知识百科。你需要利用前面筛选的农业领域内容生成农业领域相关基础知识的百科问答。

---

# 第一步：农业领域判定（必须首先执行）

**重要：在生成问答对之前，必须先判断文本内容是否属于农业领域主题。**

## 判定标准：
1. **属于农业领域（判定为"是"）**：如果文本核心内容或知识点主题属于以下任一范畴：
   - 作物生产：农作物（水稻/玉米/小麦/油菜/大豆等）和经济作物栽培与耕作、遗传育种
   - 畜牧养殖：家畜家禽的遗传育种与繁殖、营养与饲料科学
   - 植物保护：植物病理、农业昆虫与害虫防治
   - 园艺学：果树学、蔬菜学、茶学等

2. **不属于农业领域（判定为"否"）**：如果文本主要内容与上述农业相关主题无关

---

# 核心要求

1. **原子化事实**：每个问题应针对一个具体的知识点
2. **真实性原则**：严格基于文本内容，严禁编造

---

# 任务要求

基于以下条目标题和内容，生成1-2个问答对。

## 问题生成规则
- 基于文本内容，不要超出文本的范围
- 问题要清晰、有意义
- 问题必须独立可理解

## 答案生成规则
- 优先使用文本中明确提及的事实、数据等信息
- 严禁编造任何数据

---

# 输出格式

如果判定为"是"，请严格按以下JSON格式输出：

```json
{{"qa_pairs": [{{"question": "问题内容", "answer": "答案内容"}}]}}
```

如果判定为"否"，请返回：

```json
{{"qa_pairs": []}}
```

---

# 输入内容

条目标题：{title}

文本内容：
{text_content}
"""

def split_think_content(raw_answer: str):
    """从字符串中提取 <think>...</think> 内容"""
    if not raw_answer:
        return raw_answer, ""

    # 使用原始字符串匹配 think 标签
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    m = pattern.search(raw_answer)
    if not m:
        return raw_answer.strip(), ""

    think_content = m.group(1).strip()
    clean_answer = (raw_answer[:m.start()] + raw_answer[m.end():]).strip()
    return clean_answer, think_content


def extract_json_from_text(text: str):
    """从文本中提取JSON对象"""
    if not text:
        raise ValueError("输入文本为空")

    text = text.strip()

    # 方法1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 方法2：移除markdown代码块
    if text.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # 方法3：查找 { 和 } 之间的内容
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从文本中提取有效的JSON对象")


def extract_title_and_text(item):
    """从数据项中提取标题和text字段"""
    title = ""
    text_content = ""

    if isinstance(item, dict):
        # 提取标题
        for field in ['title', 'name', '名称']:
            if field in item and item[field]:
                title = str(item[field]).strip()
                if title:
                    break

        # 提取text字段
        original_data = item.get("original_data")
        if isinstance(original_data, dict):
            text = original_data.get("text")
            if text:
                if isinstance(text, str):
                    text_content = text.strip()
                elif isinstance(text, (list, tuple)):
                    text_content = " ".join([str(x) for x in text if isinstance(x, str)]).strip()

        # 如果original_data中没有，尝试直接获取
        if not text_content and 'text' in item and item['text']:
            text_value = item['text']
            if isinstance(text_value, str):
                text_content = text_value.strip()
    else:
        text_content = str(item)

    return title, text_content


def generate_qa_for_text(title: str, text: str, max_retries: int = 3) -> list:
    """基于文本生成问答对"""
    if not text or len(text.strip()) < 50:
        return []

    prompt = QA_GENERATION_PROMPT.format(title=title, text_content=text[:10000])

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )

            result_text = response.choices[0].message.content.strip()
            print(f"   模型响应长度: {len(result_text)} 字符")

            # 提取 COT
            clean_text, think_content = split_think_content(result_text)

            # 解析 JSON
            try:
                result_json = extract_json_from_text(clean_text)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"   ⚠️ JSON解析失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return []

            qa_pairs = result_json.get("qa_pairs", [])

            # 添加 COT
            if think_content and isinstance(qa_pairs, list):
                for qa in qa_pairs:
                    if isinstance(qa, dict) and not qa.get("cot"):
                        qa["cot"] = think_content

            return qa_pairs

        except Exception as e:
            print(f"   ⚠️ API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return []

    return []


def main():
    print("=" * 60)
    print("Wiki 问答对生成 - 测试版本 (版本2)")
    print("=" * 60)
    print(f"数据目录: {SAMPLE_DATA_DIR}")
    print(f"输出文件: {OUTPUT_FILE}")
    print()

    # 确保输出目录存在
    os.makedirs(os.path.dirname(OUTPUT_FILE) if os.path.dirname(OUTPUT_FILE) else ".", exist_ok=True)

    # 获取所有 JSON 文件
    json_files = sorted([f for f in os.listdir(SAMPLE_DATA_DIR) if f.endswith('.json')])
    print(f"找到 {len(json_files)} 个数据文件\n")

    total_qa = 0
    total_items = 0

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
        for idx, filename in enumerate(json_files, 1):
            filepath = os.path.join(SAMPLE_DATA_DIR, filename)

            # 读取数据
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    item = json.load(f)
            except Exception as e:
                print(f"[{idx}/{len(json_files)}] 读取文件失败: {filename}, 错误: {e}")
                continue

            title, text = extract_title_and_text(item)
            total_items += 1

            print(f"[{idx}/{len(json_files)}] 处理: {title[:50]}...")
            print(f"   text长度: {len(text)} 字符")

            # 生成问答对
            qa_pairs = generate_qa_for_text(title, text)

            if qa_pairs:
                print(f"   ✅ 生成 {len(qa_pairs)} 个问答对")

                for qa in qa_pairs:
                    qa["generation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    qa["source_file"] = filename
                    qa["title"] = title
                    out_f.write(json.dumps(qa, ensure_ascii=False) + '\n')

                total_qa += len(qa_pairs)
            else:
                print(f"   ⏭️ 未生成问答对")

            print()

    print("=" * 60)
    print("处理完成!")
    print(f"处理数据条目: {total_items}")
    print(f"生成问答对: {total_qa}")
    print(f"输出文件: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
