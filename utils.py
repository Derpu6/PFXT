# utils.py
import streamlit as st
import os
import json
import time
import re
import hashlib
import difflib
from datetime import datetime
from collections import defaultdict

# --- 全局配置 ---
CONFIG_DIR = "exam_configs"
PLAGIARISM_DIR = "plagiarism_data"
RESULTS_DIR = "exam_results"
REFLECTIONS_DIR = "student_reflections"
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(PLAGIARISM_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(REFLECTIONS_DIR, exist_ok=True)


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
        'language': "c",
        'reflection_content': "",
        'reflection_analysis': "",
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
    code_files = [f for f in os.listdir(plagiarism_dir) if f.endswith('.c') or f.endswith('.py')]
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


def save_results(student_id, student_name, config, scores, comments, ai_feedback, code_content, language="c",
                 reflection_content="", reflection_analysis=""):
    """保存评分结果 - 支持Python和心得体会"""
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

    # 保存心得体会
    if reflection_content:
        result["reflection_content"] = reflection_content
        result["reflection_analysis"] = reflection_analysis

        # 单独保存心得体会文件
        reflection_file = os.path.join(REFLECTIONS_DIR,
                                       f"{student_id}_{student_name}_{config['exam_name']}_reflection.json")
        with open(reflection_file, 'w', encoding='utf-8') as f:
            json.dump({
                "student_id": student_id,
                "student_name": student_name,
                "exam_name": config['exam_name'],
                "exam_date": config['exam_date'],
                "reflection_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "reflection_content": reflection_content,
                "reflection_analysis": reflection_analysis
            }, f, indent=2, ensure_ascii=False)

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