# config_management.py
import streamlit as st
import json
import os
import datetime
from ai_integration import ai_generate_exam_config

CONFIG_DIR = "exam_configs"

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
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
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