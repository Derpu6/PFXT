import streamlit as st
import os
import json
import time
import re
import ast
import pandas as pd
import numpy as np
import altair as alt
import hashlib
import difflib
from datetime import datetime
from collections import defaultdict
import dashscope
from dashscope import Generation
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# --- 全局配置 ---
CONFIG_DIR = "exam_configs"
PLAGIARISM_DIR = "plagiarism_data"
RESULTS_DIR = "exam_results"
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(PLAGIARISM_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


# --- 初始化Session State ---
def init_session_state():
    """初始化session状态"""
    defaults = {
        'exam_config': None,
        'student_code': "",
        'scores': {},
        'comments': {},
        'api_key': "",
        'ai_feedback': {},
        'student_id': "",
        'student_name': "",
        'design_task': None,
        'language': "c",  # 新增：默认语言
        'app_state': {
            'is_admin': False,
            'show_stats': False,
            'switch_time': time.time(),
            'memory': None,
            'messages': [],
            'mcu_model': "51单片机"
        }
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if st.session_state['app_state']['memory'] is None:
        st.session_state['app_state']['memory'] = {
            'chat_history': [{"role": "assistant", "content": "你好！我是单片机助手，请问你有什么问题？"}]
        }


# --- Qwen模型集成 ---
class QwenChat:
    def __init__(self, api_key):
        self.api_key = api_key

    def invoke(self, messages):
        """调用Qwen模型"""
        dashscope_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                dashscope_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                dashscope_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                dashscope_messages.append({"role": "assistant", "content": msg.content})

        try:
            response = Generation.call(
                model="qwen-plus",
                messages=dashscope_messages,
                temperature=0.3,
                api_key=self.api_key
            )

            if response.status_code != 200:
                raise Exception(f"API Error ({response.status_code}): {response.message}")

            return AIMessage(content=response.output.text)
        except Exception as e:
            raise Exception(f"调用Qwen模型失败: {str(e)}")


# --- 工具函数 ---
def analyze_code(code_content, language="c"):
    """分析代码质量 - 增强支持Python"""
    analysis = {
        "line_count": 0,
        "comment_count": 0,
        "comment_ratio": 0,
        "function_count": 0,
        "avg_function_length": 0,
        "issues": []
    }

    if not code_content:
        return analysis

    try:
        # 基本统计
        lines = code_content.split('\n')
        analysis["line_count"] = len(lines)

        # 语言特定分析
        if language == "python":
            # Python注释统计
            analysis["comment_count"] = sum(1 for line in lines if line.strip().startswith('#'))
            analysis["comment_ratio"] = analysis["comment_count"] / len(lines) * 100 if lines else 0

            try:
                tree = ast.parse(code_content)
                functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                analysis["function_count"] = len(functions)

                # 计算函数长度
                func_lengths = []
                for func in functions:
                    func_lengths.append(func.end_lineno - func.lineno)

                if func_lengths:
                    analysis["avg_function_length"] = sum(func_lengths) / len(func_lengths)

                # Python特定问题检测
                if "eval(" in code_content:
                    analysis["issues"].append("⚠️ 安全风险: 使用eval()函数")
                if "exec(" in code_content:
                    analysis["issues"].append("⚠️ 安全风险: 使用exec()函数")
                if any("import *" in line for line in lines):
                    analysis["issues"].append("⚠️ 代码规范: 避免使用通配符导入")

            except Exception as e:
                analysis["error"] = f"Python解析错误: {str(e)}"
        else:
            # C/C++注释统计
            analysis["comment_count"] = code_content.count("//") + code_content.count("/*")
            analysis["comment_ratio"] = analysis["comment_count"] / len(lines) * 100 if lines else 0

            try:
                # C/C++结构分析
                function_pattern = r'\w+\s+\w+\([^)]*\)\s*{'
                functions = re.findall(function_pattern, code_content)
                analysis["function_count"] = len(functions)

                # 其他C/C++特定分析...
                if "malloc" in code_content and code_content.count("malloc") > code_content.count("free"):
                    analysis["issues"].append("⚠️ 资源泄漏风险: 内存分配与释放不匹配")
            except Exception:
                pass

        # 通用问题检测
        if analysis["comment_count"] == 0:
            analysis["issues"].append("⚠️ 缺少注释")

        if analysis["function_count"] < 3:
            analysis["issues"].append("⚠️ 模块化不足: 函数数量过少")

        if analysis.get("avg_function_length", 0) > 30:
            analysis["issues"].append("⚠️ 函数过长: 建议拆分函数")

    except Exception as e:
        analysis["error"] = f"代码分析错误: {str(e)}"

    return analysis


def calculate_code_similarity(code1, code2):
    """计算两个代码的相似度"""
    matcher = difflib.SequenceMatcher(None, code1, code2)
    return matcher.ratio() * 100


def calculate_hash(code):
    """计算代码哈希值（用于预筛选）"""
    # 标准化代码：移除空格、注释和变量名
    normalized = re.sub(r'#.*?\n', '', code)  # 移除Python单行注释
    normalized = re.sub(r'//.*?\n', '', normalized)  # 移除C单行注释
    normalized = re.sub(r'/\*.*?\*/', '', normalized, flags=re.DOTALL)  # 移除多行注释
    normalized = re.sub(r'\'\'\'.*?\'\'\'', '', normalized, flags=re.DOTALL)  # 移除Python多行注释
    normalized = re.sub(r'""".*?"""', '', normalized, flags=re.DOTALL)  # 移除Python多行注释
    normalized = re.sub(r'\s+', '', normalized)  # 移除所有空白
    normalized = re.sub(r'[a-zA-Z_][a-zA-Z0-9_]*', 'var', normalized)  # 标准化变量名
    return hashlib.md5(normalized.encode()).hexdigest()


def prefilter_codes(codes):
    """使用哈希值预筛选相似代码"""
    hash_map = defaultdict(list)
    for student, code in codes.items():
        code_hash = calculate_hash(code)
        hash_map[code_hash].append(student)

    return [group for group in hash_map.values() if len(group) > 1]


def analyze_plagiarism_for_exam(exam_name):
    """分析指定评分的抄袭情况 - 支持Python文件"""
    plagiarism_dir = os.path.join(PLAGIARISM_DIR, exam_name)
    if not os.path.exists(plagiarism_dir):
        return None, "没有找到该评分的提交记录"

    # 获取所有代码文件（支持.c和.py）
    code_files = [f for f in os.listdir(plagiarism_dir) if f.endswith(('.c', '.py'))]
    if len(code_files) < 2:
        return None, "提交数量不足，无法进行抄袭分析"

    # 读取所有代码
    codes = {}
    for file in code_files:
        file_path = os.path.join(plagiarism_dir, file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                codes[file] = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    codes[file] = f.read()
            except Exception as e:
                print(f"读取文件{file_path}失败: {str(e)}")

    # 哈希预筛选
    hash_groups = prefilter_codes(codes)
    high_similarity_pairs = []

    for group in hash_groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                student1 = group[i]
                student2 = group[j]
                similarity = calculate_code_similarity(codes[student1], codes[student2])

                if similarity > 80:
                    high_similarity_pairs.append({
                        "学生1": student1.replace('.c', '').replace('.py', ''),
                        "学生2": student2.replace('.c', '').replace('.py', ''),
                        "相似度": similarity
                    })

    return high_similarity_pairs, None


def generate_similarity_report(exam_name):
    """生成抄袭情况报告"""
    high_similarity_pairs, error = analyze_plagiarism_for_exam(exam_name)

    if error:
        return None, error

    report = {
        "exam_name": exam_name,
        "high_similarity_pairs": high_similarity_pairs,
        "total_pairs": len(high_similarity_pairs)
    }

    return report, None


def ai_generate_exam_config(task_content, api_key):
    """使用AI生成评分配置 - 支持Python项目"""
    if not api_key:
        return None

    prompt = f"""
你是一位编程课程专家，请根据以下项目设计任务书生成适合初学者的评分题目配置。
请注意：学生可能提交多种语言代码（C/Python），评分应关注核心功能实现和代码质量。

**任务书内容**:
{task_content[:2500]}

**请生成包含1-3道题目的评分配置，格式要求**:
{{
  "exam_name": "评分名称",
  "exam_date": "YYYY-MM-DD",
  "questions": [
    {{
      "title": "题目标题",
      "description": "题目描述",
      "total": 分值,
      "subtasks": [
        {{"desc": "功能点描述", "score": 分值}},
        ...
      ],
      "code_criteria": ["代码质量要求1", "代码质量要求2"]
    }},
    ...
  ]
}}

**注意事项**:
1. 题目应关注核心功能实现，语言无关
2. 题目总分设置为85分（加上15分代码质量分，总计100分）
3. 评分标准要适合初学者，难度适中
4. 功能点应关注:
   - 是否正确进行初始化/设置
   - 主逻辑实现
   - 模块化设计（函数/类划分）
   - 基本错误处理
5. 代码质量要求应关注:
   - 代码结构清晰
   - 基本注释
   - 命名合理
   - 代码简洁性
6. 避免过于严格的要求，考虑初学者水平

**示例配置(Python项目)**:
{{
  "exam_name": "数据处理项目",
  "exam_date": "2023-11-15",
  "questions": [
    {{
      "title": "数据加载与处理",
      "description": "实现数据加载和处理功能",
      "total": 50,
      "subtasks": [
        {{"desc": "正确加载数据文件", "score": 15}},
        {{"desc": "实现数据清洗功能", "score": 20}},
        {{"desc": "数据转换处理", "score": 15}}
      ],
      "code_criteria": ["代码结构清晰", "基本注释完整", "变量命名合理"]
    }},
    {{
      "title": "数据分析功能",
      "description": "实现基本数据分析功能",
      "total": 35,
      "subtasks": [
        {{"desc": "实现统计计算功能", "score": 15}},
        {{"desc": "数据可视化输出", "score": 20}}
      ],
      "code_criteria": ["函数封装合理", "模块化设计"]
    }}
  ]
}}
"""

    try:
        qwen = QwenChat(api_key=api_key)
        messages = [
            SystemMessage(content="你是一名经验丰富的编程教学专家，擅长为初学者设计合理的评分题目"),
            HumanMessage(content=prompt)
        ]
        response = qwen.invoke(messages)

        try:
            config = json.loads(response.content)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if match:
                config = json.loads(match.group(0))
            else:
                raise ValueError("无法解析AI返回的JSON")

        return validate_and_adjust_config(config)
    except Exception as e:
        st.error(f"AI生成配置失败: {str(e)}")
        return None


def validate_and_adjust_config(config):
    """验证并调整配置使其适合初学者"""
    total_score = sum(q['total'] for q in config['questions'])
    if total_score != 85:
        scale = 85 / total_score
        for q in config['questions']:
            q['total'] = round(q['total'] * scale)

    if len(config['questions']) > 3:
        config['questions'] = config['questions'][:3]

    for q in config['questions']:
        if len(q['subtasks']) > 4:
            q['subtasks'] = q['subtasks'][:4]

        if len(q['code_criteria']) > 3:
            q['code_criteria'] = q['code_criteria'][:3]

        for subtask in q['subtasks']:
            if subtask['score'] > 20:
                subtask['score'] = 20

    return config


def ai_assistant_score(question, student_code, api_key, language="c"):
    """AI辅助评分 - 支持Python"""
    if not api_key:
        return "错误: 请先输入API密钥"

    # 根据语言添加特定要求
    lang_specific = ""
    if language == "python":
        lang_specific = "\n**Python特定要求**:\n- 符合PEP8代码规范\n- 使用适当的异常处理\n- 避免使用eval()和exec()\n- 使用Pythonic的写法"

    prompt = f"""
你是一位编程课程评分专家，请根据以下题目要求评估学生代码：

**题目**: {question['title']}
**描述**: {question['description']}
**功能点要求**:{lang_specific}
"""
    for idx, subtask in enumerate(question['subtasks']):
        prompt += f"    {idx + 1}. {subtask['desc']} (分值: {subtask['score']}分)\n"

    prompt += f"""
**代码质量要求**: {', '.join(question['code_criteria'])}

**学生代码**: {student_code[:5000]} 

**请严格按照以下格式给出评分建议**：
1. **功能点完成情况**（每项功能点单独评估）：
   - 功能点1: [实现情况描述] (得分: x/y)
   - 功能点2: [实现情况描述] (得分: x/y)
   ...
2. **代码质量评估**：
   - 优点: [列出代码的优点]
   - 改进建议: [列出需要改进的地方]
3. **总体评价与建议**:

你的回答必须严格按照上述格式，不要添加其他内容。
"""

    try:
        qwen = QwenChat(api_key=api_key)
        messages = [
            SystemMessage(content="你是一名经验丰富的软件工程师，擅长评估学生代码质量"),
            HumanMessage(content=prompt)
        ]
        response = qwen.invoke(messages)
        return response.content
    except Exception as e:
        return f"AI评分失败: {str(e)}"


def create_exam_config_ui():
    """创建评分配置界面"""
    st.header("📝 创建评分配置")

    if 'exam_config' not in st.session_state or st.session_state.exam_config is None:
        st.session_state.exam_config = {
            'exam_name': '',
            'exam_date': '',
            'questions': [],
            'code_criteria': ["代码结构清晰", "注释完整", "变量命名合理"],
            'code_scores': [5, 5, 5]
        }

    config = st.session_state.exam_config
    questions = config.get('questions', [])

    st.subheader("1. 上传项目设计任务书")
    uploaded_task = st.file_uploader("上传PDF/DOCX任务书", type=['pdf', 'docx'])

    if uploaded_task is not None:
        try:
            task_content = f"上传文件: {uploaded_task.name} (内容提取需实际实现)"
            st.session_state.design_task = task_content
            st.success("任务书已上传!")
        except Exception as e:
            st.error(f"文件处理错误: {str(e)}")

    if st.button("🤖 AI生成评分配置", disabled=not st.session_state.get('design_task', None)):
        with st.spinner("AI正在生成评分配置..."):
            config = ai_generate_exam_config(
                st.session_state.design_task,
                st.session_state.api_key
            )
            if config:
                st.session_state.exam_config = config
                st.success("评分配置生成成功!")
                st.rerun()

    st.subheader("2. 调整评分配置")
    if not st.session_state.get('exam_config', None):
        st.warning("请先上传任务书并生成配置")
        return None

    config = st.session_state.exam_config
    questions = config.get('questions', [])

    col1, col2 = st.columns(2)
    with col1:
        exam_name = st.text_input("评分名称", value=config.get('exam_name', ''))
    with col2:
        exam_date = st.text_input("评分日期", value=config.get('exam_date', ''))

    st.session_state.exam_config['exam_name'] = exam_name
    st.session_state.exam_config['exam_date'] = exam_date

    st.subheader("全局代码质量要求")
    code_criteria = config.get('code_criteria', ["代码结构清晰", "注释完整", "变量命名合理"])
    code_scores = config.get('code_scores', [5, 5, 5])

    if len(code_scores) < len(code_criteria):
        code_scores.extend([5] * (len(code_criteria) - len(code_scores)))

    for j, criterion in enumerate(code_criteria):
        col1, col2 = st.columns([3, 1])
        with col1:
            crit_desc = st.text_input(f"要求 {j + 1}", value=criterion, key=f"crit_{j}_desc")
        with col2:
            crit_score = st.number_input("分值", 1, 100,
                                         value=code_scores[j] if j < len(code_scores) else 5,
                                         key=f"crit_{j}_score")

        if j < len(code_criteria):
            code_criteria[j] = crit_desc
        if j < len(code_scores):
            code_scores[j] = crit_score

    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ 添加要求", key="add_crit"):
            code_criteria.append("新要求")
            code_scores.append(5)
            st.session_state.exam_config['code_criteria'] = code_criteria
            st.session_state.exam_config['code_scores'] = code_scores
            st.rerun()
    with col2:
        if len(code_criteria) > 1 and st.button("➖ 删除要求", key="del_crit"):
            code_criteria.pop()
            code_scores.pop()
            st.session_state.exam_config['code_criteria'] = code_criteria
            st.session_state.exam_config['code_scores'] = code_scores
            st.rerun()

    st.session_state.exam_config['code_criteria'] = code_criteria
    st.session_state.exam_config['code_scores'] = code_scores

    st.subheader("题目配置")

    for i, q in enumerate(questions):
        with st.expander(f"题目 {i + 1}: {q['title']}", expanded=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                title = st.text_input("标题", value=q['title'], key=f"q{i}_title")
            with col2:
                total = st.number_input("总分", 1, 100, value=q['total'], key=f"q{i}_total")

            description = st.text_area("描述", value=q['description'],
                                       height=100, key=f"q{i}_desc")

            st.session_state.exam_config['questions'][i]['title'] = title
            st.session_state.exam_config['questions'][i]['total'] = total
            st.session_state.exam_config['questions'][i]['description'] = description

            st.markdown("**功能点**")
            subtasks = q.get('subtasks', [])
            allocated_score = 0

            for j, subtask in enumerate(subtasks):
                current_score = st.session_state.exam_config['questions'][i]['subtasks'][j]['score']
                allocated_score += current_score

            for j, subtask in enumerate(subtasks):
                col1, col2 = st.columns([4, 1])
                with col1:
                    desc = st.text_input(f"功能点 {j + 1} 描述", value=subtask['desc'], key=f"q{i}_sub{j}_desc")
                with col2:
                    max_score_val = q['total'] - allocated_score + subtask['score']
                    max_score = max(0, max_score_val)
                    initial_value = min(subtask['score'], max_score) if max_score > 0 else 0
                    score = st.number_input(
                        "分值", 0, max_score, value=initial_value, key=f"q{i}_sub{j}_score"
                    )
                    allocated_score = allocated_score - subtask['score'] + score

                st.session_state.exam_config['questions'][i]['subtasks'][j]['desc'] = desc
                st.session_state.exam_config['questions'][i]['subtasks'][j]['score'] = score
                st.caption(f"已分配: {allocated_score}/{q['total']} | 剩余: {q['total'] - allocated_score}")

            if allocated_score > q['total']:
                st.warning("⚠️ 功能点总分已超过题目设定！请调整分值")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("➕ 添加功能点", key=f"q{i}_add_sub"):
                    st.session_state.exam_config['questions'][i]['subtasks'].append({"desc": "新功能点", "score": 5})
                    st.rerun()
            with col2:
                if len(subtasks) > 1 and st.button("➖ 删除功能点", key=f"q{i}_del_sub"):
                    st.session_state.exam_config['questions'][i]['subtasks'].pop()
                    st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ 添加新题目"):
            st.session_state.exam_config['questions'].append({
                "title": f"题目 {len(questions) + 1}",
                "description": "",
                "total": 20,
                "subtasks": [{"desc": "主要功能", "score": 10}]
            })
            st.rerun()
    with col2:
        if len(questions) > 1 and st.button("➖ 删除题目"):
            st.session_state.exam_config['questions'].pop()
            st.rerun()

    if st.button("💾 保存评分配置"):
        config = {
            "exam_name": exam_name,
            "exam_date": exam_date,
            "questions": st.session_state.exam_config['questions'],
            "code_criteria": code_criteria,
            "code_scores": code_scores,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        filename = f"{exam_name}_{exam_date}.json"
        filepath = os.path.join(CONFIG_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        st.session_state.exam_config = config
        st.success(f"配置已保存: {filepath}")
        return config

    return None


def load_exam_config_ui():
    """加载评分配置界面"""
    st.header("📂 加载评分配置")

    config_files = [f for f in os.listdir(CONFIG_DIR) if f.endswith(".json")]
    if not config_files:
        st.warning("没有找到评分配置文件")
        return None

    selected_file = st.selectbox("选择评分配置", config_files)
    filepath = os.path.join(CONFIG_DIR, selected_file)

    if st.button("加载配置"):
        with open(filepath, "r", encoding='utf-8') as f:
            config = json.load(f)
            st.session_state.exam_config = config
            st.success(f"已加载配置: {config['exam_name']}")
            return config
    return None


def scoring_interface(config):
    """评分界面 - 支持Python文件"""
    if config is None:
        st.error("评分配置未加载！")
        return

    st.header(f"📝 评分 - {config['exam_name']}")
    st.caption(f"评分日期: {config['exam_date']}")

    st.subheader("学生信息")
    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("学号", value=st.session_state.get('student_id', ''))
    with col2:
        student_name = st.text_input("姓名", value=st.session_state.get('student_name', ''))
    st.session_state.student_id = student_id
    st.session_state.student_name = student_name

    st.subheader("代码提交")
    uploaded_file = st.file_uploader("上传学生代码", type=['c', 'cpp', 'h', 'py'])
    code_content = st.session_state.get('student_code', "")

    # 语言识别
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.py'):
            language = 'python'
        elif uploaded_file.name.endswith(('.cpp', '.h')):
            language = 'cpp'
        else:
            language = 'c'
        st.session_state.language = language  # 存储语言类型

    if uploaded_file is not None:
        try:
            code_content = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            try:
                code_content = uploaded_file.getvalue().decode("gbk")
                st.warning("代码文件似乎使用GBK编码，已尝试转换。请确保内容正确。")
            except UnicodeDecodeError:
                st.error("无法解码上传的文件。请确保文件是文本格式（如 .c, .cpp, .h, .py）并使用UTF-8或GBK编码。")
                code_content = ""

        if code_content:
            st.session_state.student_code = code_content
            with st.expander("查看代码", expanded=False):
                # 根据语言显示代码
                language = st.session_state.language
                if language == "python":
                    st.code(code_content, language="python")
                else:
                    st.code(code_content, language="c")

    st.subheader("评分")
    total_score = 0
    scores = {}
    comments = {}

    progress_bar = st.progress(0)
    num_questions = len(config.get('questions', []))

    if num_questions == 0:
        st.warning("评分配置中没有题目")
        return

    for i, q in enumerate(config['questions']):
        progress_value = (i + 1) / num_questions
        progress_bar.progress(progress_value)

        with st.expander(f"{q['title']} - {q['total']}分", expanded=(i == 0)):
            if code_content and st.button(f"🤖 AI辅助评分 - {q['title']}", key=f"ai_{i}", use_container_width=True):
                with st.spinner("AI评分中..."):
                    feedback = ai_assistant_score(
                        q,
                        st.session_state.student_code,
                        st.session_state.api_key,
                        language=st.session_state.language
                    )
                    st.session_state.ai_feedback[q['title']] = feedback

            if q['title'] in st.session_state.get('ai_feedback', {}):
                st.subheader("🤖 AI评分反馈")
                st.info(st.session_state.ai_feedback[q['title']])
                st.divider()

            st.markdown(f"**功能实现 ({q['total']}分)**")
            func_score = 0
            q_comments = []

            for j, subtask in enumerate(q['subtasks']):
                col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
                with col1:
                    st.markdown(f"**{subtask['desc']}**")
                with col2:
                    status = st.selectbox(
                        "完成情况",
                        ["未实现", "部分实现", "完全实现"],
                        index=["未实现", "部分实现", "完全实现"].index(
                            st.session_state.get(f"q{i}_sub{j}_status", "未实现")),
                        key=f"q{i}_sub{j}_status"
                    )
                with col3:
                    max_score = float(subtask['score'])
                    if status == "未实现":
                        score = 0.0
                    elif status == "部分实现":
                        default_partial = max_score / 2.0
                        score = st.number_input(
                            "得分",
                            0.0, max_score, st.session_state.get(f"q{i}_sub{j}_score", default_partial),
                            key=f"q{i}_sub{j}_score",
                            step=0.5
                        )
                    else:
                        score = max_score
                    st.markdown(f"**得分: {score:.1f}/{max_score}**")

                comment = st.text_area("评语", value=st.session_state.get(f"q{i}_sub{j}_comment", ""),
                                       key=f"q{i}_sub{j}_comment", height=60,
                                       placeholder="记录实现细节、问题或建议...")
                if comment:
                    q_comments.append(f"{subtask['desc']}: {comment}")

                func_score += score

            st.markdown(f"**题目得分: {func_score:.1f}/{q['total']}**")
            st.markdown("---")

            total_score += func_score
            scores[q['title']] = func_score
            comments[q['title']] = q_comments

    st.subheader("代码质量评分")
    code_criteria = config.get('code_criteria', [])
    code_scores = config.get('code_scores', [])
    code_total = sum(code_scores) if code_scores else 0

    if code_total > 0:
        st.markdown(f"**代码质量 ({code_total}分)**")
        code_score = 0
        code_comments = []

        if code_criteria and code_scores:
            for j, (criterion, max_score) in enumerate(zip(code_criteria, code_scores)):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{criterion}**")
                with col2:
                    score_val = st.number_input(
                        "得分",
                        0.0, float(max_score),
                        st.session_state.get(f"code_crit{j}_score", max_score * 0.75),
                        key=f"code_crit{j}_score",
                        step=0.5
                    )
                    st.markdown(f"**得分: {score_val:.1f}/{max_score}**")

                comment = st.text_area(f"{criterion}评语",
                                       value=st.session_state.get(f"code_crit{j}_comment", ""),
                                       key=f"code_crit{j}_comment", height=60,
                                       placeholder="记录代码质量评估...")
                if comment:
                    code_comments.append(f"{criterion}: {comment}")

                code_score += score_val
        else:
            st.warning("⚠️ 未配置代码质量评分标准")
            code_score = st.slider(
                "代码质量评分",
                0.0, 20.0, st.session_state.get("code_score", 15.0),
                key="code_score",
                step=0.5
            )

            code_comment = st.text_area("代码质量评语", value=st.session_state.get("code_comment", ""),
                                        key="code_comment", height=80,
                                        placeholder="记录代码结构、风格、优化建议等...")
            if code_comment:
                code_comments.append(f"代码质量: {code_comment}")

        if code_content:
            analysis = analyze_code(code_content, language=st.session_state.language)

            st.caption("代码分析结果:")
            col1, col2, col3 = st.columns(3)
            col1.metric("代码行数", analysis["line_count"])
            col2.metric("注释数量", analysis["comment_count"])
            col3.metric("注释比例", f"{analysis['comment_ratio']:.1f}%")

            col1, col2 = st.columns(2)
            col1.metric("函数数量", analysis["function_count"])
            col2.metric("平均函数长度", f"{analysis['avg_function_length']:.1f}行")

            if "issues" in analysis and analysis["issues"]:
                st.warning("潜在问题检测")
                for issue in analysis["issues"]:
                    st.write(issue)

        st.markdown(f"**代码质量得分: {code_score:.1f}/{code_total}**")
        st.markdown("---")

        total_score += code_score
        scores["代码质量"] = code_score
        comments["代码质量"] = code_comments
    else:
        st.warning("⚠️ 未配置代码质量评分标准")

    st.session_state.scores = scores
    st.session_state.comments = comments

    st.subheader("成绩概览")
    st.metric("总分", f"{total_score:.1f}")

    st.subheader("提交评分")
    if st.button("✅ 提交评分", use_container_width=True, type="primary"):
        st.session_state.total_score = total_score

        if student_id and student_name:
            try:
                result_file = save_results(
                    student_id, student_name, config,
                    st.session_state.scores,
                    st.session_state.comments,
                    st.session_state.get('ai_feedback', {}),
                    code_content,
                    st.session_state.language
                )
                st.success(f"✅ 评分结果已保存至: {result_file}", icon="🎉")
            except Exception as e:
                st.error(f"❌ 保存评分结果时出错: {e}")
        else:
            st.warning("⚠️ 请填写学号和姓名后再提交。")


def save_results(student_id, student_name, config, scores, comments, ai_feedback, code_content, language="c"):
    """保存评分结果 - 支持Python"""
    result = {
        "student_id": student_id,
        "student_name": student_name,
        "exam_name": config['exam_name'],
        "exam_date": config['exam_date'],
        "score_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_score": sum(scores.values()),
        "scores": scores,
        "comments": comments,
        "ai_feedback": ai_feedback,
        "language": language
    }

    student_dir = f"{student_id}_{student_name}"
    os.makedirs(student_dir, exist_ok=True)

    student_result_file = os.path.join(student_dir, f"{config['exam_name']}_result.json")
    with open(student_result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    result_file = os.path.join(RESULTS_DIR, f"{student_id}_{student_name}_{config['exam_name']}_result.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    if code_content:
        # 根据语言保存不同扩展名
        ext = "py" if language == "python" else "c"
        code_file = os.path.join(student_dir, f"{config['exam_name']}_code.{ext}")
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code_content)

        plagiarism_dir = os.path.join(PLAGIARISM_DIR, config['exam_name'])
        os.makedirs(plagiarism_dir, exist_ok=True)
        plagiarism_file = os.path.join(plagiarism_dir, f"{student_id}_{student_name}.{ext}")
        with open(plagiarism_file, 'w', encoding='utf-8') as f:
            f.write(code_content)

    return result_file


def show_learning_feedback():
    """显示学情反馈界面"""
    st.header("📊 学情反馈")

    if st.session_state.exam_config is None:
        st.warning("请先加载或创建一个评分配置！")
        return

    exam_name = st.session_state.exam_config['exam_name']
    st.subheader(f"当前评分: {exam_name}")

    st.subheader("班级整体表现")

    if not os.path.exists(RESULTS_DIR):
        st.warning("没有找到任何评分结果数据")
        return

    result_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".json")]
    if not result_files:
        st.warning("没有找到任何评分结果文件")
        return

    exam_results = []
    for file in result_files:
        if exam_name in file:
            filepath = os.path.join(RESULTS_DIR, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                result = json.load(f)
                exam_results.append(result)

    if not exam_results:
        st.warning(f"没有找到'{exam_name}'的评分结果")
        return

    students = []
    scores = []
    for result in exam_results:
        students.append(f"{result['student_id']}_{result['student_name']}")
        scores.append(result['total_score'])

    avg_score = np.mean(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("平均分", f"{avg_score:.1f}")
    col2.metric("最高分", max_score)
    col3.metric("最低分", min_score)

    st.write("学生成绩分布:")
    chart_data = pd.DataFrame({'学生': students, '分数': scores})
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('学生', sort=None),
        y='分数',
        color=alt.value('skyblue')
    ).properties(width=600, height=300)
    text = chart.mark_text(align='center', baseline='bottom', dy=-5).encode(text='分数')
    st.altair_chart(chart + text)

    st.subheader("成绩分布分析")
    st.write(f"- 优秀 (≥90分): {len([s for s in scores if s >= 90])}人")
    st.write(f"- 良好 (80-89分): {len([s for s in scores if 80 <= s < 90])}人")
    st.write(f"- 中等 (70-79分): {len([s for s in scores if 70 <= s < 80])}人")
    st.write(f"- 及格 (60-69分): {len([s for s in scores if 60 <= s < 70])}人")
    st.write(f"- 不及格 (<60分): {len([s for s in scores if s < 60])}人")

    st.subheader("班级强项与弱项分析")
    topic_scores = {}
    topic_counts = {}
    question_map = {
        q["title"]: q["total"]
        for q in st.session_state.exam_config.get("questions", [])
    }

    for result in exam_results:
        for topic, score in result["scores"].items():
            if topic == "代码质量":
                total = st.session_state.exam_config.get("code_total", 15)
            else:
                total = question_map.get(topic, 100)
            score_rate = (score / total) * 100 if total > 0 else 0

            if topic not in topic_scores:
                topic_scores[topic] = 0
                topic_counts[topic] = 0

            topic_scores[topic] += score_rate
            topic_counts[topic] += 1

    topics = []
    avg_topic_scores = []
    for topic, total_score in topic_scores.items():
        count = topic_counts[topic]
        avg_score = total_score / count
        topics.append(topic)
        avg_topic_scores.append(avg_score)

    strong_topics = []
    weak_topics = []
    for i, score in enumerate(avg_topic_scores):
        if score >= 85:
            strong_topics.append(topics[i])
        elif score < 70:
            weak_topics.append(topics[i])

    col1, col2 = st.columns(2)
    with col1:
        st.success("**班级强项**")
        if strong_topics:
            for topic in strong_topics:
                st.write(f"- {topic} (得分率: {avg_topic_scores[topics.index(topic)]:.1f}%)")
        else:
            st.write("暂无显著强项")
    with col2:
        st.warning("**班级弱项**")
        if weak_topics:
            for topic in weak_topics:
                st.write(f"- {topic} (得分率: {avg_topic_scores[topics.index(topic)]:.1f}%)")
        else:
            st.write("暂无显著弱项")

    st.subheader("各题目得分率")
    topic_df = pd.DataFrame({'题目': topics, '平均得分率': avg_topic_scores})
    chart = alt.Chart(topic_df).mark_bar().encode(
        x=alt.X('题目', sort=None, axis=alt.Axis(labelAngle=45)),
        y=alt.Y('平均得分率', scale=alt.Scale(domain=[0, 100])),
        color=alt.Color('平均得分率:Q',
                        scale=alt.Scale(domain=[0, 70, 85, 100],
                                        range=['red', 'skyblue', 'green', 'green']),
                        legend=None)
    ).properties(width=600, height=400)
    rule_85 = alt.Chart(pd.DataFrame({'y': [85]})).mark_rule(color='green', strokeDash=[5, 5]).encode(y='y')
    rule_70 = alt.Chart(pd.DataFrame({'y': [70]})).mark_rule(color='red', strokeDash=[5, 5]).encode(y='y')
    text = chart.mark_text(align='center', baseline='bottom', dy=-5).encode(text=alt.Text('平均得分率:Q', format='.1f'))
    st.altair_chart(chart + rule_85 + rule_70 + text)

    st.subheader("个人分数分析")
    selected_student = st.selectbox("选择学生", students)
    student_result = None
    for result in exam_results:
        if f"{result['student_id']}_{result['student_name']}" == selected_student:
            student_result = result
            break

    if not student_result:
        st.warning("找不到该学生的详细结果")
        return

    st.metric(f"{selected_student}的分数", f"{student_result['total_score']}分")
    st.write("具体表现:")
    col1, col2 = st.columns(2)
    with col1:
        st.info("**强项**")
        strong_topics = []
        for topic, score in student_result['scores'].items():
            for q in st.session_state.exam_config.get('questions', []):
                if q['title'] == topic:
                    total = q['total']
                    break
            else:
                total = 100
            score_rate = (score / total) * 100
            if score_rate >= 85:
                strong_topics.append(f"{topic} ({score_rate:.1f}%)")
        if strong_topics:
            for topic in strong_topics:
                st.write(f"- {topic}")
        else:
            st.write("暂无显著强项")
    with col2:
        st.warning("**弱项**")
        weak_topics = []
        for topic, score in student_result['scores'].items():
            for q in st.session_state.exam_config.get('questions', []):
                if q['title'] == topic:
                    total = q['total']
                    break
            else:
                total = 100
            score_rate = (score / total) * 100
            if score_rate < 70:
                weak_topics.append(f"{topic} ({score_rate:.1f}%)")
        if weak_topics:
            for topic in weak_topics:
                st.write(f"- {topic}")
        else:
            st.write("暂无显著弱项")


def show_plagiarism_report():
    """显示抄袭情况报告"""
    st.header("🔍 抄袭情况分析")

    exam_names = [d for d in os.listdir(PLAGIARISM_DIR) if os.path.isdir(os.path.join(PLAGIARISM_DIR, d))]
    if not exam_names:
        st.warning("没有找到任何作业的抄袭数据")
        return

    selected_exam = st.selectbox("选择作业", exam_names)

    if st.button("分析抄袭情况"):
        with st.spinner("正在分析抄袭情况..."):
            report, error = generate_similarity_report(selected_exam)

        if error:
            st.warning(error)
            return

        st.subheader(f"作业: {selected_exam}")
        st.caption(f"高相似度配对数量: {report['total_pairs']}")

        if report['high_similarity_pairs']:
            st.subheader("高相似度配对 (相似度 > 80%)")
            for pair in report['high_similarity_pairs']:
                st.warning(f"⚠️ {pair['学生1']} 和 {pair['学生2']} 的代码相似度高达 {pair['相似度']:.1f}%")

            st.subheader("高相似度学生对比")
            df = pd.DataFrame(report['high_similarity_pairs'])
            st.dataframe(df)

            st.subheader("相似度分布")
            similarities = [pair['相似度'] for pair in report['high_similarity_pairs']]
            sim_df = pd.DataFrame({'相似度': similarities})
            chart = alt.Chart(sim_df).mark_bar(color='salmon').encode(
                alt.X('相似度:Q', bin=alt.Bin(maxbins=10), title='相似度 (%)'),
                alt.Y('count()', title='配对数量'),
            ).properties(width=600, height=300)
            st.altair_chart(chart)
        else:
            st.success("✅ 没有发现高相似度代码")

    st.subheader("抄袭检测建议")
    st.write("1. 加强代码审查和人工检查")
    st.write("2. 使用更先进的抄袭检测工具")
    st.write("3. 对学生进行学术诚信教育")
    st.write("4. 设计更具个性化的编程题目")
    st.write("5. 增加面试环节验证学生理解程度")


if __name__ == "__main__":
    init_session_state()
    st.sidebar.title("导航")

    st.sidebar.subheader("AI API密钥设置")
    api_key = st.sidebar.text_input("输入AI API密钥", type="password",
                                    value=st.session_state.get('api_key', ''),
                                    help="从阿里云DashScope平台获取")
    st.session_state.api_key = api_key

    app_mode = st.sidebar.selectbox("选择模式", ["评分界面", "创建评分配置", "学情反馈", "抄袭情况"])

    st.sidebar.markdown("---")
    st.sidebar.subheader("加载评分配置")
    config_files = [f for f in os.listdir(CONFIG_DIR) if f.endswith(".json")]
    if config_files:
        selected_file = st.sidebar.selectbox("选择评分配置", config_files)
        filepath = os.path.join(CONFIG_DIR, selected_file)
        if st.sidebar.button("加载配置"):
            with open(filepath, "r", encoding='utf-8') as f:
                config = json.load(f)
                st.session_state.exam_config = config
                st.sidebar.success(f"已加载配置: {config['exam_name']}")
    else:
        st.sidebar.warning("没有找到评分配置文件")

    if app_mode == "创建评分配置":
        config = create_exam_config_ui()
        if config:
            st.session_state.exam_config = config
            st.success("评分配置已创建并加载!")
    elif app_mode == "评分界面":
        if st.session_state.exam_config:
            scoring_interface(st.session_state.exam_config)
        else:
            st.warning("请先在侧边栏加载评分配置")
    elif app_mode == "学情反馈":
        if st.session_state.exam_config:
            show_learning_feedback()
        else:
            st.warning("请先在侧边栏加载评分配置")
    elif app_mode == "抄袭情况":
        show_plagiarism_report()
