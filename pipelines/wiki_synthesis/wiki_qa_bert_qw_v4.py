"""
Wiki数据筛选与问答对生成工具
功能：
1. 从.json文件中读取Wiki数据
2. 使用OpenAI从数据中提取关键内容并生成问答对
3. 保存为JSONL文件
"""

from openai import OpenAI
import json
import os
import time
import re
import copy
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
import csv
import shutil

# ==== API 配置 ====
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("请在.env文件中设置OPENAI_API_KEY")
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

# 千问API配置
# 使用说明：
# 1. 在.env文件中添加 QWEN_API_KEY=你的千问API密钥
# 2. 如果使用阿里云DashScope，默认base_url为：https://dashscope.aliyuncs.com/compatible-mode/v1
# 3. 如果使用其他服务商的千问API，请在.env文件中设置 QWEN_BASE_URL=你的API地址
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
if QWEN_API_KEY:
    qwen_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    print(f"✅ 已加载千问API配置，base_url: {QWEN_BASE_URL}")
else:
    print("⚠️  警告：未设置QWEN_API_KEY，千问模型将使用默认client（可能失败）")
    qwen_client = client  # 回退到默认client

# ==== 配置参数 ====
DEFAULT_MODEL = "gpt-5.1"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8000
BATCH_SIZE = 10  # 每批处理的数据量
QUOTA_STATE_FILE = "quota_exhausted_state.json"  # 记录令牌额度用尽时的进度状态文件

# 千问大模型（用于二次农业领域判定）的模型名称（请根据实际部署情况修改）
# 阿里云DashScope常用模型名称：
# - qwen-turbo
# - qwen-plus
# - qwen-max
# - qwen-flash
# 如果使用其他服务商的千问API，请根据实际模型名称修改
QWEN_MODEL = "qwen-flash"

# ==== 文件路径配置（请根据实际情况修改） ====
BATCH = os.getenv("WIKI_BATCH", "bert_qw_qa_batch_5")
VERSION = "v4.0"
WIKI_DATA_DIR = os.getenv("WIKI_DATA_DIR", f"agricultural_content/{BATCH}")
OUTPUT_CSV = f"wiki_{BATCH}_{VERSION}.csv"  # 输出CSV文件路径
# 千问农业判定为1的文件暂存目录
QWEN_POSITIVE_DIR = os.getenv("WIKI_QWEN_POSITIVE_DIR", "bert_qw_dedup")
# ==== 运行模式配置 ====
# 可选值：
#   "both" - 运行阶段1和阶段2（默认）
#   "stage1" - 仅运行阶段1（千问判定并复制文件）
#   "stage2" - 仅运行阶段2（从目标目录读取文件生成问答对）
RUN_MODE = "stage2"  # 运行模式

# ==== 文件处理范围配置 ====
# 如果只想处理部分文件，可以设置以下参数：
# FILE_START_INDEX: 起始文件索引（从1开始，1表示第一个文件）
# FILE_END_INDEX: 结束文件索引（包含该索引，None表示处理到最后一个文件）
#
# 使用示例：
#   1. 处理前10个文件：
#      FILE_START_INDEX = 1
#      FILE_END_INDEX = 10
#
#   2. 处理第11到第20个文件：
#      FILE_START_INDEX = 11
#      FILE_END_INDEX = 20
#
#   3. 处理第50个文件到最后一个文件：
#      FILE_START_INDEX = 50
#      FILE_END_INDEX = None
#
#   4. 处理所有文件（默认行为）：
#      FILE_START_INDEX = 1
#      FILE_END_INDEX = None
#
# 注意：
#   - 文件会按照文件路径的字母顺序排序后进行处理
#   - 阶段1和阶段2都使用这些配置参数
#   - 如果存在恢复点（quota_exhausted_state.json），阶段2会优先从恢复点继续，但会受配置范围限制
FILE_START_INDEX = 8001  # 起始文件索引（从1开始）
FILE_END_INDEX = 10000  # 结束文件索引（None表示处理到最后）


class TokenQuotaExceededError(Exception):
    """自定义异常：表示调用 API 时令牌额度已用尽，需要停止程序并记录进度。"""


# ==== 读取JSON文件 ====
def read_json(file_path: str) -> List[Dict]:
    """
    读取.json文件，返回JSON对象列表
    已知所有JSON文件都是单个JSON对象，直接读取并解析
    text内容通过original_data.get("text")获取
    """
    print(f"📖 正在读取JSON文件: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print(f"⚠️  文件为空，返回空列表")
                return []
            
            # 直接解析为单个JSON对象
            data = json.loads(content)
            
            # 统一转换为列表格式
            if isinstance(data, list):
                data_list = data
            else:
                data_list = [data]
            
            # print(f"✅ 读取完成，共 {len(data_list)} 条记录")
            return data_list
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {e}")
    except Exception as e:
        raise Exception(f"读取JSON文件失败: {e}")


def save_quota_state(current_json_file: str, output_jsonl_path: str) -> None:
    """
    在令牌额度用尽时，记录当前处理到的文件信息，便于下次从该文件重新开始。
    目前记录：
      - last_json_file: 最后一个处理（发生额度用尽）的JSON文件完整路径
      - output_jsonl: 当前输出JSONL文件路径
      - timestamp: 保存时间
    """
    state = {
        "last_json_file": current_json_file,
        "output_jsonl": output_jsonl_path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(QUOTA_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"💾 已记录令牌额度用尽状态到: {QUOTA_STATE_FILE}")
        print(f"   - last_json_file: {current_json_file}")
    except Exception as e:
        print(f"⚠️ 保存令牌额度状态失败: {e}")


def load_quota_state() -> str:
    """
    读取上一次令牌额度用尽时记录的状态。
    返回 last_json_file（字符串），如果不存在或解析失败则返回空字符串。
    """
    if not os.path.exists(QUOTA_STATE_FILE):
        return ""
    try:
        with open(QUOTA_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        last_json_file = state.get("last_json_file", "") or ""
        if last_json_file:
            print(f"🔁 检测到上次令牌额度用尽记录，将尝试从该文件重新开始: {last_json_file}")
        return last_json_file
    except Exception as e:
        print(f"⚠️ 读取令牌额度状态文件失败，将忽略该状态: {e}")
        return ""


def extract_text_field(item: Dict) -> str:
    """
    提取text字段，优先从original_data.get("text")获取
    这是wiki内容的主要字段来源
    """
    if not isinstance(item, dict):
        return str(item)
    
    # 优先从original_data.get("text")获取（主要数据源）
    original_data = item.get("original_data")
    if isinstance(original_data, dict):
        text = original_data.get("text")
        if text:
            if isinstance(text, str):
                return text
            elif isinstance(text, (list, tuple)):
                # 如果text是列表，拼接所有字符串元素
                return " ".join([str(x) for x in text if isinstance(x, str)])
    
    # 如果original_data中没有，尝试直接获取text字段
    if "text" in item and item["text"]:
        text_value = item["text"]
        if isinstance(text_value, str):
            return text_value
        elif isinstance(text_value, (list, tuple)):
            return " ".join([str(x) for x in text_value if isinstance(x, str)])
    
    # 如果text字段不存在，尝试从metadata中获取
    if "metadata" in item and isinstance(item["metadata"], dict):
        metadata = item["metadata"]
        # 尝试 metadata.wikipedia.text
        if "wikipedia" in metadata and isinstance(metadata["wikipedia"], dict):
            wiki_data = metadata["wikipedia"]
            if "text" in wiki_data and wiki_data["text"]:
                text_value = wiki_data["text"]
                if isinstance(text_value, str):
                    return text_value
        
        # 尝试 metadata.wikipedia.passage
        if "wikipedia" in metadata and isinstance(metadata["wikipedia"], dict):
            wiki_data = metadata["wikipedia"]
            if "passage" in wiki_data and wiki_data["passage"]:
                text_value = wiki_data["passage"]
                if isinstance(text_value, str):
                    return text_value
    
    # 兜底：尝试其他可能的文本字段
    for field in ["content", "body", "description"]:
        if field in item and item[field]:
            value = item[field]
            if isinstance(value, str) and len(value) > 50:
                return value
    
    return ""


# ==== 生成问答对的Prompt模板 ====
QA_GENERATION_PROMPT = """# 角色定位

你是一个农业领域专家，通晓农业领域基础知识百科。你需要利用前面筛选的农业领域内容生成农业领域相关基础知识的百科问答。

---

# 第一步：农业领域判定（必须首先执行）

**重要：在生成问答对之前，必须先判断文本内容是否属于农业领域主题。**

## 判定标准：
1. **属于农业领域（判定为"是"）**：如果文本核心内容或知识点主题属于以下任一范畴：
   - 作物生产：农作物（水稻/玉米/小麦/油菜/大豆等）和经济作物（苹果/梨/桃/香蕉/橡胶/椰子/咖啡等）栽培与耕作、遗传育种、种子科学与技术、作物信息、品种特性、育种技术、病虫草害防治、田间作业规范
   - 畜牧养殖：家畜家禽（牛/猪/羊/鸡/鸭/马等）的遗传育种与繁殖、营养与饲料科学、特种经济动物饲养、畜牧生物工程、品种选育、饲养管理、疫病防控、养殖技术
   - 植物保护：植物病理、农业昆虫与害虫防治、农药学、生物防治
   - 兽医学：基础兽医学、预防兽医学、临床兽医学、兽医公共卫生
   - 园艺学：果树学（水果）、蔬菜学（蔬菜）、茶学（茶叶）、观赏园艺学（花卉）等
   - 林学：森林培育（林木）、森林保护学、森林经理学、野生动物保护与利用、园林植物与观赏园艺等
   - 水产：水产养殖、捕捞学、渔业资源、水产品加工与贮藏
   - 草学：草地资源与生态、饲草学、草地保护学
   - 农业资源与环境：土壤学、植物营养学、农业环境保护、资源利用与植物保护
   - 农业科学基础：与农业生产相关的植物学、动物学、微生物学、生态学、生命科学基础（遗传学、基因组学、发育生物学、生物化学与分子生物学等）等知识
   - 农业生态系统：土壤科学、水资源管理、气候变化适应、生物多样性保护
   - 农业可持续发展：循环农业、绿色生产、碳中和农业、可持续农业

2. **不属于农业领域（判定为"否"）**：如果文本主要内容与上述农业相关主题无关（如纯粹人文社科、金融、互联网技术、通用数理、医学临床、娱乐八卦、非农业工业生产等）

3. **多学科交叉处理**：当文本涉及多学科交叉时，如果农业相关内容只是顺带提及、不是核心主题或主要知识点，则判定为"否"；只有当农业内容是文本的核心关注点或主要说明对象时，才判定为"是"。

## 判定结果处理：
- **如果判定为"否"（非农业领域）**：直接返回空数组，不要生成任何问答对
  ```json
  {{
    "qa_pairs": []
  }}
  ```

- **如果判定为"是"（农业领域）**：继续执行后续的问答对生成流程

---

# 核心要求（必须严格遵守）

1. **原子化事实 (Atomic Facts)**：
    *   **问题知识点化**： 每个问题应针对一个具体的知识点（如：某品种的抗病性、某技术的具体参数）。
    *   **答案细节化**： 答案应包含原文中的具体细节（数据、年份、特定名称）。

2.  **真实性原则（最高优先级）**
    *   **严格基于文本内容**：你的回答必须完全基于当前提供的文本内容。严禁使用文本中未提及的任何信息，包括行业标准、研究成果或生产实践（除非这些信息在文本中明确提及）。
    *   **禁止任何形式的编造**：严禁任何形式的推测、想象、编造或补充。即使某些信息在专业上是常识或标准做法，如果文本中没有提及，也不得添加到答案中。
    *   **信息不完整时的处理**：如果文本信息不足以完整回答问题，必须如实说明"根据提供的信息，[具体说明哪些方面无法回答]"，而不是编造或推测缺失的信息。
    *   **零容忍造假**：严禁捏造任何文献、数据、品种名称、实验结果、具体案例、年份、地点或任何其他事实性信息。

3.  **边界原则**
    *   **信息不足时的处理**：如果当前文本中的信息不足以完整回答问题，必须如实说明"根据提供的信息，[具体说明哪些方面无法回答或信息不足]"，而不是编造、推测或使用外部知识补充。
    *   **不越界指导**：绝不提供文本中未提及的具体操作指导、实验方法或技术细节。如果文本中提到了某个方法或技术，只能基于文本中的描述进行说明，不得添加文本中未提及的步骤或细节。


## 禁止使用的引用性表达

在生成问题和答案时，**绝对禁止**使用以下任何引用性词语或表达方式：

**禁止的词语和短语：**
- "文中"、"文中认为"、"文中提到"、"文中围绕"、"文中指出"、"文中说明"、 "书中"、"该植物"、"该配方"
- "从提供的资料"、"根据提供的资料"、"资料显示"、"资料表明"
- "根据文本"、"文本显示"、"文本表明"、"文本提到"
- "wiki"、"Wiki"、"Wiki文本"、"Wiki内容"、"Wiki显示"
- "内容显示"、"内容表明"、"内容提到"、"内容指出"
- "上述内容"、"以上内容"、"该内容"、"这些内容"
- "来源显示"、"来源表明"、"来源提到"
- 任何暗示引用或转述的表达方式



**核心原则：**
- 问题和答案都要像直接的知识陈述，而不是对文本的引用
- 直接描述事实和知识，就像你在直接回答用户的问题一样
- 使用第一人称或客观陈述，避免任何引用性表述
- 答案必须独立完整，不能出现依赖任何上下文才能回答的答案

---

# 任务要求（一次性完成）

**重要：这是一次性任务，请同时生成问题和对应的答案，不要分步骤进行。**

---

基于以下条目标题和内容，**一次性同时生成1-2个问答对**：

## 问题生成规则
- **基于文本内容**：百科的问题需要基于当前提供的文本内容，不要超出文本的范围
- **清晰有意义**：问题要清晰、有意义，能够帮助读者理解农业领域的基础知识
- **独立可理解**：问题必须独立可理解，不依赖任何上下文或第三方知识
    - 问题本身必须包含完整的语义信息，读者在只看到问题本身的情况下，也能准确理解问题指向的对象和含义
    - 不要出现需要对第三方知识的依赖和引用
- **直接客观**：问题必须直接、客观，不包含任何引用性词语
- **语言选择**：可以根据文本内容选择使用中文或英文生成问题，但必须确保问题和答案使用同一种语言

## 答案生成规则

**答案生成要求：**

1. **主要信息来源**：
   - 百科的答案必须使用当前文本内容作为主要信息来源
   - 优先使用文本中明确提及的事实、数据、名称、方法等信息
   - 如果文本中提到了具体数据、年份、名称等，必须在答案中准确呈现

2. **专业知识补充（谨慎使用）**：
   - 如果提供的文本内容过少或不够全面，不足以完整、全面回答当前问题，可以结合你的农学、生物科学、育种学专业知识进行适当补充和完善
   - 补充的目的是使答案更完整、更专业，避免答案过于笼统或绝对或缺少关键点
   - 补充的内容必须与文本内容相关，且符合农业领域基础知识

3. **严禁编造（最高优先级）**：
   - **最重要的一点：答案严禁无任何数据依据的编造、推测和想象**
   - 严禁编造任何数据、年份、品种名称、实验结果、文献引用
   - 严禁基于猜测或假设进行补充，即使这些补充在专业上是合理的
   - 所有补充的内容必须基于专业知识的一般规律，且不能与文本内容冲突

4. **答案质量要求**：
   - 避免答案过于笼统：答案应该具体、详细，包含关键信息点
   - 避免答案过于绝对：使用适当的表述，避免绝对化的断言
   - 避免缺少关键点：确保答案包含回答问题的核心要素
   - 结构清晰，逻辑完整，使用准确的农业领域专业术语

5. **独立完整性**：
   - 答案必须独立完整，不依赖任何上下文
   - 答案中提到的所有概念、术语、数据、名称都必须在当前文本中有明确依据，或基于专业知识的一般规律
   - 禁止使用代词（如"它"、"这个"、"上述"等）指代文本中未在当前答案中明确说明的内容
   - 如果必须提及某个概念，必须在答案中直接说明该概念是什么

6. **语言匹配原则（必须严格遵守）**：
   * **如果问题是中文**：答案必须用中文回答，使用中文专业术语
   * **如果问题是英文**：答案必须用英文回答，使用英文专业术语
   * **问题和答案的语言必须完全一致**，不允许混用语言

7. **表达要求**：
   - 答案应该像直接的知识陈述，就像你在直接回答用户的问题一样
   - 必须直接、客观地陈述事实，不包含任何引用性词语


---

# 输出格式（JSON格式）

请严格按照以下JSON格式输出，不要添加任何额外的说明文字。

**重要：** 请按照以下逻辑执行：

1. **首先判定**：判断文本是否属于农业领域主题
   - 如果判定为"否"（非农业领域），直接返回：
     ```json
     {{
       "qa_pairs": []
     }}
     ```
   - 如果判定为"是"（农业领域），继续执行步骤2

2. **生成问答对**：如果判定为"是"，按照下面的格式生成 **1-2 个问答对**：
   ```json
   {{
     "qa_pairs": [
       {{
         "question": "问题内容（直接、客观的问题，不包含引用性词语）",
         "answer": "答案内容（直接、客观的知识陈述，不包含任何引用性词语，语言必须与问题语言一致）",
         "cot": "为得到答案所进行的关键思考与推理过程的总结（请控制在合理长度，不要包含与结论无关的冗长思考细节）",
         "topic": "知识点主题（如：品种特性、育种方法、栽培技术等）"
       }}
     ]
   }}
   ```

**语言匹配要求**：
- 如果问题使用中文，答案必须使用中文
- 如果问题使用英文，答案必须使用英文
- 问题和答案的语言必须完全一致

**返回空数组的情况**：
- 文本不属于农业领域主题（必须返回空数组）
- 确实无法从文本中提出有意义的问题（可以返回空数组）

---

# 条目标题

{title}

---

# 内容

{text_content}

---

请严格遵循以上所有要求：
1. **首先判断文本是否属于农业领域主题**：如果判定为"否"，直接返回空数组 `{{"qa_pairs": []}}`，不要生成任何问答对
2. **如果判定为"是"**：基于当前文本内容生成 1-2 个高质量的农业领域基础知识百科问答对
3. **问题要求**：基于文本内容、清晰有意义、独立可理解、不依赖第三方知识
4. **答案要求**：
   - 必须使用当前文本内容作为主要信息来源
   - 如果文本内容不足，可以结合专业知识适当补充，使答案更完整、更专业
   - 避免答案过于笼统、绝对或缺少关键点
   - **严禁无任何数据依据的编造、推测和想象**
5. **问答中绝对不包含任何引用性词语**
6. **语言匹配：问题的语言必须与答案的语言完全一致（中文问题用中文回答，英文问题用英文回答）**

**重要提醒**：
- 请务必先执行农业领域判定，只有判定为"是"时才生成问答对，判定为"否"时直接返回空数组
- 答案补充专业知识时，必须确保有依据，严禁无数据依据的编造、推测和想象"""


# ==== 千问农业领域判定提示词（请根据需要自行完善） ====
# 使用说明：
# - 请在运行前，将 AGRI_CLASSIFICATION_PROMPT 的内容替换为你自己提供的中文提示词
# - 要求模型对给定 text 判断是否为“农业领域相关内容”
# - 约定输出：若是农业领域相关内容，返回 "1"；否则返回 "0"
AGRI_CLASSIFICATION_PROMPT = """ 你是位资深农业领域专家，精通农作物、畜禽的栽培育种，掌握经济作物栽培、植物保护、兽医学、园艺学、林学、水产养殖、草学和农业资源与环境农业等农学相关知识；
了解遗传学、基因组学、发育生物学、生物化学与分子生物学、生物物理学、神经生物学、水生生物学、生物物理学、生理学等生命科学基础知识。\n\n
        现在请你只做一件事：判断一段中文或英文文本的'主要知识主题'是否属于农业领域。\n\n
        判定标准说明（请严格遵守）：\n
        1. 若文本核心内容或知识点主题属于以下任一范畴，则判定为农业领域（输出 1）：
        - 作物生产：农作物（水稻/玉米/小麦/油菜/大豆等和经济作物（苹果/梨/桃/香蕉/橡胶/椰子/咖啡等）栽培与耕作、遗传育种、种子科学与技术、作物信息、品种特性、育种技术、病虫草害防治、田间作业规范；
        - 畜牧养殖：家畜家禽（牛/猪/羊/鸡/鸭/马等）的遗传育种与繁殖、营养与饲料科学、特种经济动物饲养、畜牧生物工程、品种选育、饲养管理、疫病防控、养殖技术；
        - 植物保护：植物病理、农业昆虫与害虫防治、农药学、生物防治；
        - 兽医学： 基础兽医学、预防兽医学、临床兽医学、兽医公共卫生；
        - 园艺学： 果树学（水果）、蔬菜学（蔬菜）、茶学（茶叶）、观赏园艺学（花卉）等；
        - 林学： 森林培育（林木）、森林保护学、森林经理学、野生动物保护与利用、园林植物与观赏园艺等；
        - 水产： 水产养殖、捕捞学、渔业资源、水产品加工与贮藏； 
        - 草学： 草地资源与生态、饲草学、草地保护学；
        - 农业资源与环境： 土壤学、植物营养学、农业环境保护、资源利用与植物保护；
        - 农业科学基础：包括但不限于以下内容均属于农业领域：
            - 植物学知识：主要限于农作物或与农业生产相关植物的分类、形态特征、生物学特性、生态习性、分布范围、生长环境、用途介绍等；
            - 动物学知识：主要限于家畜家禽或与农业生产相关动物的分类、形态特征、生物学特性、生态习性、分布范围、栖息环境、行为习性等；
            - 微生物学知识：与农业相关的微生物（如土壤微生物、发酵微生物、病原微生物等）的分类、特性、功能等；
            - 生态学知识：生态系统、生物多样性、物种间关系、生态平衡、环境因子对生物的影响等；
            - 生命科学基础：发育生物学、生物化学与分子生物学、生物物理学、神经生物学、水生生物学、生物物理学、生理学、生物信息学、遗传学、基因组学、分子生物学、细胞生物学等与农业应用相关的基础学科知识；
            - 农学相关学科：育种学、栽培学、土壤学、植物保护学、动物营养学、兽医学等；
        - 农业生态系统：土壤科学/水资源管理/气候变化适应/生物多样性保护;
        - 农业可持续发展：循环农业/绿色生产/碳中和农业/可持续农业;
        则视为'农业领域'，输出 1。\n
        2. 若文本主要内容与上述农业相关主题无关（如纯粹人文社科、金融、互联网技术、通用数理、医学临床、娱乐八卦、非农业工业生产等），判定为'非农业领域'，输出 0\n
        3. 当文本涉及多学科交叉时，如果农业相关内容只是顺带提及、不是核心主题或主要知识点，则判定为 0；只有当农业内容是文本的核心关注点或主要说明对象时，才判定为 1。\n
        4. 不要求细分是作物学、畜牧学、植物保护、兽医学、园艺学、林学、水产养殖、草学和农业资源与环境农业等农学相关知识，只要整体主题属于农业领域，即可判定为 1，否则输出 0\n\n
        输出要求（务必严格遵守）：\n
        - 只输出一个阿拉伯数字：'1' 或 '0'。\n
        - 不要输出任何解释、理由或其他符号、文字。\n\n
        f"下面是需要判断的文本：\n{text}"
"""


# ==== 工具：解析 <think> 中的 COT ====
def split_think_content(raw_answer: str) -> Tuple[str, str]:
    """
    从字符串中提取 <think>...</think> 内容
    返回：(clean_answer, think_content)

    说明：
    - clean_answer：去掉 <think> 块之后的剩余内容（本脚本中期望是纯 JSON 字符串）
    - think_content：<think> ... </think> 中的内容（作为 COT 保存）
    """
    if not raw_answer:
        return raw_answer, ""

    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    m = pattern.search(raw_answer)
    if not m:
        return raw_answer.strip(), ""

    think_content = m.group(1).strip()
    clean_answer = (raw_answer[:m.start()] + raw_answer[m.end():]).strip()
    return clean_answer, think_content


# ==== 工具：从文本中提取JSON对象 ====
def extract_json_from_text(text: str) -> Dict:
    """
    从可能包含额外内容的文本中提取JSON对象
    支持多种格式：
    1. 纯JSON字符串
    2. Markdown代码块包裹的JSON
    3. JSON前后有额外文本
    4. 不完整的JSON（尝试修复）
    """
    if not text:
        raise ValueError("输入文本为空")
    
    original_text = text
    text = text.strip()
    
    # 方法1：尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 方法2：移除markdown代码块标记
    if text.startswith("```"):
        # 移除开头的 ```json 或 ```
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        # 移除结尾的 ```
        cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
    
    # 方法3：查找第一个 { 和最后一个 } 之间的内容（最可靠的方法）
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError as e:
            # 如果JSON不完整，尝试修复常见问题
            # 检查是否缺少闭合括号
            open_count = json_candidate.count('{')
            close_count = json_candidate.count('}')
            if open_count > close_count:
                # 添加缺失的闭合括号
                json_candidate += '}' * (open_count - close_count)
                try:
                    return json.loads(json_candidate)
                except json.JSONDecodeError:
                    pass
    
    # 方法4：尝试查找包含 "qa_pairs" 的JSON对象
    # 这通常是我们需要的格式
    qa_pairs_match = re.search(r'\{[^{}]*"qa_pairs"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if qa_pairs_match:
        json_candidate = qa_pairs_match.group(0)
        # 尝试扩展匹配，找到完整的JSON对象
        start_pos = qa_pairs_match.start()
        # 从匹配位置向前查找第一个 {，向后查找最后一个 }
        extended_start = text.rfind('{', 0, start_pos + 1)
        if extended_start != -1:
            # 从扩展的起始位置查找匹配的 }
            brace_count = 0
            for i in range(extended_start, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_candidate = text[extended_start:i+1]
                        try:
                            return json.loads(json_candidate)
                        except json.JSONDecodeError:
                            break
    
    # 方法5：使用递归方法查找最外层的JSON对象
    # 从第一个 { 开始，找到匹配的最后一个 }
    first_brace = text.find('{')
    if first_brace != -1:
        brace_count = 0
        for i in range(first_brace, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_candidate = text[first_brace:i+1]
                    try:
                        return json.loads(json_candidate)
                    except json.JSONDecodeError:
                        break
    
    # 如果所有方法都失败，抛出异常并显示更多信息
    # 创建一个更友好的错误消息
    error_details = []
    error_details.append("无法从文本中提取有效的JSON对象")
    error_details.append(f"文本长度: {len(original_text)} 字符")
    error_details.append(f"文本前300字符: {original_text[:300]}")
    if len(original_text) > 300:
        error_details.append(f"文本后300字符: {original_text[-300:]}")
    
    # 检查是否包含 "qa_pairs" 关键字
    if '"qa_pairs"' in original_text or "'qa_pairs'" in original_text:
        error_details.append("检测到 'qa_pairs' 关键字，但JSON格式可能不完整")
        # 尝试找到 qa_pairs 附近的内容
        qa_pos = original_text.find('qa_pairs')
        if qa_pos != -1:
            start = max(0, qa_pos - 100)
            end = min(len(original_text), qa_pos + 200)
            error_details.append(f"qa_pairs 附近内容: {original_text[start:end]}")
    
    error_msg = "\n   ".join(error_details)
    # 使用 ValueError 而不是 JSONDecodeError，因为文本可能根本不是有效的JSON
    raise ValueError(error_msg)


# ==== 使用千问模型进行农业领域判定 ====
def classify_agriculture_by_qwen(text: str, max_retries: int = 2) -> int:
    """
    使用千问大模型对文本进行“是否为农业领域相关内容”的判定。
    返回：
        1 -> 是农业领域相关内容
        0 -> 否，或判定失败
    """
    if not text or not text.strip():
        return 0

    prompt = AGRI_CLASSIFICATION_PROMPT.format(text=text[:4000])

    for attempt in range(max_retries):
        try:
            response = qwen_client.chat.completions.create(
                model=QWEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=10,
            )
            content = response.choices[0].message.content.strip()
            print(f"千问判定返回内容--->: {content}")
            # 只提取第一个 0/1 字符
            m = re.search(r"[01]", content)
            if not m:
                print(f"⚠️ 千问判定返回内容无法解析为 0/1：{content!r}")
                continue
            return 1 if m.group(0) == "1" else 0
        except Exception as e:
            print(f"⚠️ 千问农业判定调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            else:
                return 0

    return 0


# ==== 调用OpenAI生成问答对 ====
def generate_qa_pairs_from_title_and_text(title: str, text_content: str, max_retries: int = 3) -> List[Dict]:
    """
    基于标题和文本内容生成问答对
    """
    # 限制文本内容长度
    text_content_limited = text_content[:10000] if len(text_content) > 10000 else text_content
    prompt = QA_GENERATION_PROMPT.format(
        title=title[:500] if len(title) > 500 else title,  # 限制标题长度
        text_content=text_content_limited
    )
    
    for attempt in range(max_retries):
        try:
            # 注意：当前后端不支持额外的 reasoning / think 参数，
            # 因此仅通过 Prompt 让模型在返回结果中包含 `cot` 字段
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 调试：打印原始响应（前500字符）
            if attempt == 0:  # 只在第一次尝试时打印
                print(f"📥 模型原始响应（前500字符）: {result_text[:500]}")
                print(f"📥 模型原始响应（后500字符）: {result_text[-500:] if len(result_text) > 500 else result_text}")

            # 先从 <think>...</think> 中提取 COT，并去掉 think 块，保留纯 JSON 字符串
            clean_text, think_content = split_think_content(result_text)
            
            # 使用改进的JSON提取函数
            try:
                result_json = extract_json_from_text(clean_text)
            except (json.JSONDecodeError, ValueError) as json_err:
                print(f"⚠️ JSON提取失败 (尝试 {attempt + 1}/{max_retries})")
                print(f"   错误类型: {type(json_err).__name__}")
                print(f"   错误信息: {str(json_err)}")
                if hasattr(json_err, 'msg'):
                    print(f"   错误详情: {json_err.msg}")
                if hasattr(json_err, 'pos'):
                    print(f"   错误位置: {json_err.pos}")
                print(f"   清理后的文本（前500字符）: {clean_text[:500]}")
                print(f"   清理后的文本（后500字符）: {clean_text[-500:] if len(clean_text) > 500 else clean_text}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    print(f"❌ 无法提取JSON，跳过此条数据")
                    return []
            
            qa_pairs = result_json.get("qa_pairs", [])

            # 如果模型没有在 JSON 中显式给出 cot 字段，则回退使用 <think> 中的内容
            if think_content and isinstance(qa_pairs, list):
                for qa in qa_pairs:
                    if isinstance(qa, dict):
                        cot_in_json = qa.get("cot")
                        if not cot_in_json:
                            qa["cot"] = think_content
            
            return qa_pairs
            
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            print(f"   错误位置: 行 {e.lineno}, 列 {e.colno}")
            if attempt == max_retries - 1:  # 最后一次尝试时打印更多信息
                print(f"   原始响应（前500字符）: {result_text[:500] if 'result_text' in locals() else 'N/A'}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                print(f"❌ 无法解析响应，跳过此条数据")
                return []
        except Exception as e:
            err_msg = str(e)
            # 检测令牌额度/配额相关错误，立即抛出自定义异常，交由上层停止程序并记录进度
            if "insufficient_quota" in err_msg or "exceeded your current quota" in err_msg or "quota" in err_msg.lower():
                print("❌ 检测到令牌额度已用尽，将停止后续处理并记录当前文件信息。")
                raise TokenQuotaExceededError(err_msg)

            print(f"⚠️ API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return []
    
    return []


# ==== 提取标题和文本内容 ====
def extract_title_and_text(item: Dict) -> tuple:
    """
    从数据项中提取标题和text字段内容
    返回: (title, text_content)
    """
    title = ""
    text_content = ""
    
    if isinstance(item, dict):
        # 提取标题（优先从多个可能的字段获取）
        title_fields = ['title', 'metadata.wikipedia.title', 'metadata.wikipedia.passage', 
                       'name', '名称', 'subject', '主题']
        
        # 先尝试直接字段
        for field in ['title', 'name', '名称', 'subject', '主题']:
            if field in item and item[field]:
                title = str(item[field]).strip()
                if title:
                    break
        
        # 如果没找到，尝试从metadata中获取
        if not title and 'metadata' in item and isinstance(item['metadata'], dict):
            metadata = item['metadata']
            if 'wikipedia' in metadata and isinstance(metadata['wikipedia'], dict):
                wiki_data = metadata['wikipedia']
                for field in ['title', 'passage']:
                    if field in wiki_data and wiki_data[field]:
                        title = str(wiki_data[field]).strip()
                        if title:
                            break
        
        # 提取text字段，优先从original_data.get("text")获取（主要数据源）
        original_data = item.get("original_data")
        if isinstance(original_data, dict):
            text = original_data.get("text")
            if text:
                if isinstance(text, str):
                    text_content = text.strip()
                elif isinstance(text, (list, tuple)):
                    text_content = " ".join([str(x) for x in text if isinstance(x, str)]).strip()
        
        # 如果original_data中没有，尝试直接获取text字段
        if not text_content and 'text' in item and item['text']:
            text_value = item['text']
            if isinstance(text_value, str):
                text_content = text_value.strip()
            elif isinstance(text_value, (list, tuple)):
                text_content = " ".join([str(x) for x in text_value if isinstance(x, str)]).strip()
        
        # 如果text字段不存在，尝试从metadata.wikipedia.text获取
        if not text_content and 'metadata' in item and isinstance(item['metadata'], dict):
            metadata = item['metadata']
            if 'wikipedia' in metadata and isinstance(metadata['wikipedia'], dict):
                wiki_data = metadata['wikipedia']
                if 'text' in wiki_data and wiki_data['text']:
                    text_value = wiki_data['text']
                    if isinstance(text_value, str):
                        text_content = text_value.strip()
    else:
        text_content = str(item)
    
    return title, text_content


# ==== 处理单条数据 ====
def process_single_item(item: Dict, index: int, total: int) -> List[Dict]:
    """
    处理单条Wiki数据，基于标题生成问题，基于text内容生成答案
    直接使用text整段文本进行问答对生成
    """
    # 提取标题和text内容
    title, text_content = extract_title_and_text(item)
    original_title = title.strip() if title else ""
    
    if not text_content or len(text_content.strip()) < 50:
        print(f"⏭️  [{index}/{total}] text内容过短，跳过")
        return []

    # 如果缺少有效标题，使用文本内容生成一个临时标题（取前100个字符）
    if original_title:
        effective_title = original_title
    else:
        cleaned_text = re.sub(r'\s+', ' ', text_content).strip()
        effective_title = cleaned_text[:100] + ("..." if len(cleaned_text) > 100 else "")
        if not effective_title:
            effective_title = "未命名条目"
    
    print(f"\n📝 [{index}/{total}] 处理标题: {effective_title[:50]}...")
    print(f"   text内容长度: {len(text_content)} 字符")
    
    # 直接使用整段文本生成问答对
    try:
        # 针对整段文本生成问答对
        qa_pairs = generate_qa_pairs_from_title_and_text(effective_title, text_content)
        print(f'qa_pairs--->{qa_pairs}')
        
        if qa_pairs:
            print(f"   ✅ 生成 {len(qa_pairs)} 个问答对")
            # 添加元数据（供后续保存到 meta 中使用）
            original_data = item.get("original_data", {}) if isinstance(item, dict) else {}

            for qa in qa_pairs:
                # 保留必要的元信息
                qa["generation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                qa["original_data"] = original_data
            return qa_pairs
        else:
            # 空数组表示当前文本未能生成有效问答对
            print(f"   ⏭️  未生成问答对（返回空数组）")
            return []
    except TokenQuotaExceededError:
        # 将额度异常继续抛给上层，由上层统一处理记录和停止
        raise
    except Exception as e:
        print(f"   ⚠️ 处理失败: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"   详细错误信息:")
        traceback.print_exc()
        return []


# ==== 处理单个数据集 ====
def process_single_dataset(json_file: str, 
                          output_jsonl_path: str, file_index: int, total_files: int,
                          global_file_index: int = None, total_files_found: int = None,
                          skip_qwen_check: bool = False):
    """
    处理单个wiki数据集文件：
    1. 读取数据
    2. 直接对数据逐条进行千问判定后生成问答对（基于标题生成问题，基于text生成答案）
    3. 每生成完一条数据的问答对就立即保存到JSONL
    
    参数:
        file_index: 在当前处理范围内的相对索引
        total_files: 当前处理范围的文件总数
        global_file_index: 全局文件索引（可选，用于显示）
        total_files_found: 总文件数（可选，用于显示）
    """
    print(f"\n{'='*70}")
    if global_file_index is not None and total_files_found is not None:
        print(f"📄 处理文件 ({file_index}/{total_files}) [全局: {global_file_index}/{total_files_found}]: {os.path.basename(json_file)}")
    else:
        print(f"📄 处理文件 ({file_index}/{total_files}): {os.path.basename(json_file)}")
    print(f"{'='*70}")
    
    # 1. 读取数据
    print(f"\n📖 正在读取文件...")
    data_list = read_json(json_file)

    # print(f"✅ 读取完成，共 {len(data_list)} 条原始数据")

    if not data_list:
        print(f"⚠️  该文件无有效数据，跳过")
        return 0, 0
    
    # 2. 直接使用全部数据生成问答对（可选：跳过千问判定）
    print(f"\n🚀 开始生成问答对（{'跳过千问判定' if skip_qwen_check else '包含千问模型农业领域判定'}）...")
    total_qa_count = 0
    processed_count = 0
    all_qa_pairs = []

    for index, item in enumerate(data_list, 1):
        # ==== 3.1 使用千问模型进行农业领域判定 ====
        # 提取文本（与后续问答生成使用同一套逻辑，保证判定依据一致）
        _, text_for_check = extract_title_and_text(item)
        if not text_for_check or len(text_for_check.strip()) < 10:
            print(f"⏭️  [{index}/{len(data_list)}] 文本过短，跳过千问判定与问答生成")
            continue

        if skip_qwen_check:
            qwen_flag = 1
        else:
            qwen_flag = classify_agriculture_by_qwen(text_for_check)
            print(f'qw------->{qwen_flag}')
            if qwen_flag != 1:
                print(f"⏭️  [{index}/{len(data_list)}] 千问模型判定为非农业领域（返回 {qwen_flag}），跳过问答生成")
                continue

        # ==== 3.2 通过千问判定后再生成问答对 ====
        try:
            qa_pairs = process_single_item(item, index, len(data_list))
        except TokenQuotaExceededError:
            # 令牌额度已用尽：记录当前文件信息并向上抛出，停止后续所有处理
            save_quota_state(json_file, output_jsonl_path)
            print("⛔ 由于令牌额度已用尽，停止当前文件及后续文件的处理。")
            raise
        
        if qa_pairs:
            all_qa_pairs.extend(qa_pairs)
            total_qa_count += len(qa_pairs)
            processed_count += 1
            
            # 每生成完一条数据的问答对就立即保存
            save_qa_pairs_to_jsonl(all_qa_pairs, output_jsonl_path, append=True)
            print(f"💾 已保存 {len(all_qa_pairs)} 个问答对到JSONL (本文件累计: {total_qa_count})")
            all_qa_pairs = []  # 清空已保存的
        
        # 避免API限流，每条数据之间稍作休息
        if index < len(data_list):
            time.sleep(0.5)
    
    # 保存剩余数据（理论上应该为空，因为每生成完就保存了）
    if all_qa_pairs:
        save_qa_pairs_to_jsonl(all_qa_pairs, output_jsonl_path, append=True)
        print(f"💾 已保存剩余 {len(all_qa_pairs)} 个问答对到JSONL")
    
    print(f"\n✅ 文件处理完成！")
    print(f"   - 处理数据条数: {processed_count}/{len(data_list)}")
    print(f"   - 生成问答对总数: {total_qa_count}")
    print(f"   - 平均每条数据生成: {total_qa_count/processed_count if processed_count > 0 else 0:.2f} 个问答对")
    
    return processed_count, total_qa_count


# ==== 阶段1：仅做千问农业判定并复制文件 ====
def classify_and_copy_dataset(json_file: str, target_dir: str, file_index: int, total_files: int) -> bool:
    """
    对单个数据集文件进行千问农业判定：
    - 任意一条数据判定为1，则将整个文件复制到目标目录
    - 返回是否复制
    """
    print(f"\n{'-'*70}")
    print(f"🔍 阶段1判定文件 ({file_index}/{total_files}): {os.path.basename(json_file)}")
    print(f"{'-'*70}")

    data_list = read_json(json_file)
    if not data_list:
        print("⚠️  文件无有效数据，跳过")
        return False

    for index, item in enumerate(data_list, 1):
        _, text_for_check = extract_title_and_text(item)
        if not text_for_check or len(text_for_check.strip()) < 10:
            continue
        qwen_flag = classify_agriculture_by_qwen(text_for_check)
        print(f"   [{index}/{len(data_list)}] 千问判定结果: {qwen_flag}")
        if qwen_flag == 1:
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, os.path.basename(json_file))
            try:
                shutil.copy(json_file, target_path)
                print(f"   ✅ 判定为农业领域，已复制到: {target_path}")
                return True
            except Exception as copy_err:
                print(f"   ⚠️ 文件复制失败: {copy_err}")
                return False

    print("   ⏭️  未判定为农业领域，文件不复制")
    return False


# ==== 保存问答对到JSONL ====
def save_qa_pairs_to_jsonl(qa_pairs: List[Dict], jsonl_path: str, append: bool = False):
    """
    保存问答对到JSONL文件（每行一个JSON对象）
    """
    if not qa_pairs:
        return
    
    # 确保目录存在
    os.makedirs(os.path.dirname(jsonl_path) if os.path.dirname(jsonl_path) else '.', exist_ok=True)
    
    # 写入JSONL文件（追加模式或新建）
    mode = 'a' if append and os.path.exists(jsonl_path) else 'w'
    with open(jsonl_path, mode, encoding='utf-8') as f:
        for qa in qa_pairs:
            # 计算 COT 长度（按字符数统计）
            cot = qa.get("cot", "") or ""
            cot_length = len(cot)

            # 构建 meta 信息
            meta = {
                "cot_length": cot_length,
                "generation_time": qa.get("generation_time", ""),
                "topic": qa.get("topic", ""),
                # 将该 JSON 记录中的 original_data 整体写入 meta
                "original_data": qa.get("original_data", {}),
            }

            # 构建输出记录：question / answer / cot + meta
            record = {
                "question": qa.get("question", ""),
                "answer": qa.get("answer", ""),
                "cot": cot,
                "meta": meta,
            }

            # 写入JSON行
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ==== 阶段1：千问农业判定并复制文件 ====
def stage1_classify_and_copy():
    """
    阶段1：使用千问模型对原始目录中的文件进行农业领域判定，并将判定为农业领域的文件复制到目标目录
    """
    print("="*60)
    print("阶段1：千问农业领域判定与文件复制")
    print("="*60)
    
    wiki_data_dir = WIKI_DATA_DIR
    target_dir = QWEN_POSITIVE_DIR
    
    print(f"\n📁 Wiki数据目录: {wiki_data_dir}")
    print(f"📁 目标目录: {target_dir}")
    
    # 验证路径
    if not os.path.exists(wiki_data_dir):
        print(f"❌ 数据目录不存在: {wiki_data_dir}")
        print("   请检查 WIKI_DATA_DIR 配置是否正确")
        return False
    
    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)
    
    # 1. 查找所有.json文件
    json_files = []
    for root, dirs, files in os.walk(wiki_data_dir):
        for file in files:
            if file.endswith('.json'):
                json_files.append(os.path.join(root, file))
    
    if not json_files:
        print(f"❌ 在 {wiki_data_dir} 中未找到.json文件")
        return False
    
    # 对文件列表进行排序，确保处理顺序一致
    json_files.sort()
    
    total_files_found = len(json_files)
    print(f"\n📁 找到 {total_files_found} 个.json文件")
    
    # 2. 根据配置的文件范围筛选要处理的文件
    start_index = FILE_START_INDEX if FILE_START_INDEX is not None else 1
    end_index = FILE_END_INDEX if FILE_END_INDEX is not None else total_files_found
    
    # 验证索引范围
    if start_index < 1:
        print(f"⚠️  警告：FILE_START_INDEX ({start_index}) 小于1，已自动调整为1")
        start_index = 1
    
    if end_index > total_files_found:
        print(f"⚠️  警告：FILE_END_INDEX ({end_index}) 超过文件总数 ({total_files_found})，已自动调整为 {total_files_found}")
        end_index = total_files_found
    
    if start_index > end_index:
        print(f"❌ 错误：FILE_START_INDEX ({start_index}) 大于 FILE_END_INDEX ({end_index})")
        print("   请检查配置参数")
        return False

    # 提取要处理的文件范围（转换为0-based索引）
    files_to_process = json_files[start_index - 1:end_index]
    
    print(f"\n📋 文件处理范围配置:")
    print(f"   - 起始索引: {start_index}")
    print(f"   - 结束索引: {end_index}")
    print(f"   - 实际处理文件数: {len(files_to_process)} / {total_files_found}")
    print(f"   - 处理文件范围: 第 {start_index} 到第 {end_index} 个文件")
    
    if len(files_to_process) < total_files_found:
        print(f"   ⚠️  注意：只处理部分文件，其余文件将被跳过")
    
    # 3. 千问农业判定并复制到新目录
    copied_count = 0
    for relative_index, json_file in enumerate(files_to_process, 1):
        copied = classify_and_copy_dataset(
            json_file,
            target_dir,
            relative_index,
            len(files_to_process)
        )
        if copied:
            copied_count += 1
    
    print(f"\n{'='*70}")
    print(f"✅ 阶段1完成！")
    print(f"   - 处理文件总数: {len(files_to_process)}")
    print(f"   - 复制文件总数: {copied_count}")
    print(f"   - 目标目录: {target_dir}")
    print(f"{'='*70}\n")
    
    return copied_count > 0


# ==== 阶段2：从目标目录读取文件并生成问答对 ====
def stage2_generate_qa():
    """
    阶段2：从目标目录（QWEN_POSITIVE_DIR）读取所有文件，生成问答对
    此阶段可独立运行，不依赖阶段1的结果
    """
    print("="*60)
    print("阶段2：问答对生成")
    print("="*60)
    
    source_dir = QWEN_POSITIVE_DIR
    output_jsonl = OUTPUT_CSV.replace('.csv', '.jsonl') if OUTPUT_CSV.endswith('.csv') else OUTPUT_CSV
    
    print(f"\n📁 源数据目录: {source_dir}")
    print(f"💾 输出JSONL文件: {output_jsonl}")
    
    # 验证路径
    if not os.path.exists(source_dir):
        print(f"❌ 源数据目录不存在: {source_dir}")
        print("   请检查 QWEN_POSITIVE_DIR 配置是否正确，或先运行阶段1")
        return False
    
    # 1. 扫描目标目录中的所有.json文件
    json_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith('.json'):
                json_files.append(os.path.join(root, file))
    
    if not json_files:
        print(f"❌ 在 {source_dir} 中未找到.json文件")
        print("   请先运行阶段1进行文件筛选和复制")
        return False
    
    # 对文件列表进行排序，确保处理顺序一致
    json_files.sort()
    
    total_files_found = len(json_files)
    print(f"\n📁 找到 {total_files_found} 个.json文件")
    
    # 2. 检查是否存在上一次令牌额度用尽时记录的进度
    resume_from_file = load_quota_state()
    
    # 3. 确定文件处理范围
    # 优先考虑恢复点，然后应用配置的文件范围
    config_start_index = FILE_START_INDEX if FILE_START_INDEX is not None else 1
    config_end_index = FILE_END_INDEX if FILE_END_INDEX is not None else total_files_found
    
    # 验证配置的索引范围
    if config_start_index < 1:
        print(f"⚠️  警告：FILE_START_INDEX ({config_start_index}) 小于1，已自动调整为1")
        config_start_index = 1
    
    if config_end_index > total_files_found:
        print(f"⚠️  警告：FILE_END_INDEX ({config_end_index}) 超过文件总数 ({total_files_found})，已自动调整为 {total_files_found}")
        config_end_index = total_files_found
    
    if config_start_index > config_end_index:
        print(f"❌ 错误：FILE_START_INDEX ({config_start_index}) 大于 FILE_END_INDEX ({config_end_index})")
        print("   请检查配置参数")
        return False
    
    # 确定实际起始索引
    # 如果存在恢复点，且恢复点在配置范围内，则从恢复点开始
    # 否则使用配置的起始索引
    actual_start_index = config_start_index
    if resume_from_file and resume_from_file in json_files:
        resume_index = json_files.index(resume_from_file) + 1  # 转为1-based
        if resume_index >= config_start_index and resume_index <= config_end_index:
            print(f"\n🔁 检测到上次令牌额度用尽记录，将从该文件重新开始: 索引 {resume_index}, 文件: {os.path.basename(resume_from_file)}")
            actual_start_index = resume_index
        elif resume_index < config_start_index:
            print(f"\n⚠️  恢复点索引 ({resume_index}) 小于配置的起始索引 ({config_start_index})，将使用配置的起始索引")
        elif resume_index > config_end_index:
            print(f"\n⚠️  恢复点索引 ({resume_index}) 大于配置的结束索引 ({config_end_index})，将使用配置的起始索引")
    
    # 提取要处理的文件范围
    files_to_process = json_files[actual_start_index - 1:config_end_index]
    
    print(f"\n📋 文件处理范围配置:")
    print(f"   - 配置起始索引: {config_start_index}")
    print(f"   - 配置结束索引: {config_end_index}")
    print(f"   - 实际起始索引: {actual_start_index}")
    print(f"   - 实际结束索引: {config_end_index}")
    print(f"   - 实际处理文件数: {len(files_to_process)} / {total_files_found}")
    print(f"   - 处理文件范围: 第 {actual_start_index} 到第 {config_end_index} 个文件")
    
    if actual_start_index > config_start_index:
        print(f"   - 从上次中断位置继续处理")
    
    if len(files_to_process) < total_files_found:
        print(f"   ⚠️  注意：只处理部分文件，其余文件将被跳过")
    
    # 4. 如果输出文件已存在且不是从恢复点继续，先删除（重新开始）
    if actual_start_index == config_start_index and actual_start_index == 1 and os.path.exists(output_jsonl):
        os.remove(output_jsonl)
        print(f"🗑️  已删除旧的输出文件")
    
    # 5. 生成问答对
    total_processed = 0
    total_qa_generated = 0
    
    try:
        for relative_index, json_file in enumerate(files_to_process, 1):
            global_index = actual_start_index + relative_index - 1
            processed_count, qa_count = process_single_dataset(
                json_file, 
                output_jsonl,
                relative_index,  # 在当前处理范围内的相对索引
                len(files_to_process),  # 当前处理范围的文件总数
                global_index,  # 全局索引（用于日志显示）
                total_files_found,  # 总文件数（用于日志显示）
                skip_qwen_check=True  # 跳过千问判定，因为阶段1已经筛选过了
            )
            total_processed += processed_count
            total_qa_generated += qa_count
            
            # 文件之间稍作休息
            if relative_index < len(files_to_process):
                print(f"\n⏸️  休息2秒后处理下一个文件...")
                time.sleep(2)
    except TokenQuotaExceededError:
        # 已在下层记录了额度用尽的文件信息，这里只做统一提示并提前结束
        print("\n⛔ 检测到令牌额度已用尽，本次运行将在此处停止。")
        print("   下次重新启动脚本时，将自动从记录的文件位置重新开始处理。")
        # 不再继续处理后续文件，直接输出当前统计并返回
        print(f"\n{'='*70}")
        print(f"📊 当前进度统计（在额度用尽前）:")
        print(f"   - 阶段2文件总数: {total_files_found}")
        print(f"   - 已处理文件数: {relative_index if 'relative_index' in locals() else 0}")
        print(f"   - 处理数据总数: {total_processed}")
        print(f"   - 生成问答对总数: {total_qa_generated}")
        print(f"\n📄 输出文件（已生成部分数据）: {output_jsonl}")
        return False
    
    print(f"\n{'='*70}")
    print(f"🎉 阶段2完成！")
    print(f"{'='*70}")
    print(f"📊 统计信息:")
    print(f"   - 处理文件总数: {len(files_to_process)}")
    print(f"   - 处理数据总数: {total_processed}")
    print(f"   - 生成问答对总数: {total_qa_generated}")
    if total_processed > 0:
        print(f"   - 平均每条数据生成: {total_qa_generated/total_processed:.2f} 个问答对")
    print(f"\n📄 输出文件: {output_jsonl}")
    print(f"{'='*70}\n")
    
    return True


# ==== 主函数 ====
def main():
    """
    主处理流程
    根据RUN_MODE配置决定运行阶段1、阶段2或两者
    """
    print("="*60)
    print("Wiki数据筛选与问答对生成工具")
    print("="*60)
    print(f"\n🔧 运行模式: {RUN_MODE}")
    
    if RUN_MODE == "stage1":
        # 仅运行阶段1
        stage1_classify_and_copy()
    elif RUN_MODE == "stage2":
        # 仅运行阶段2
        stage2_generate_qa()
    elif RUN_MODE == "both":
        # 运行阶段1和阶段2
        print("\n" + "="*60)
        print("开始执行阶段1和阶段2")
        print("="*60 + "\n")
        
        # 执行阶段1
        stage1_success = stage1_classify_and_copy()
        
        if not stage1_success:
            print("\n⛔ 阶段1未找到农业领域文件，终止后续问答生成。")
            return
        
        # 执行阶段2
        stage2_generate_qa()
    else:
        print(f"❌ 错误的运行模式: {RUN_MODE}")
        print("   请设置 RUN_MODE 为 'stage1'、'stage2' 或 'both'")
        return


if __name__ == "__main__":
    main()

