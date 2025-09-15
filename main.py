# main.py
import streamlit as st
import os
import json
import time
from config_management import create_exam_config_ui, load_exam_config_ui
from scoring_interface import scoring_interface
from learning_feedback import show_learning_feedback
from plagiarism_detection import show_plagiarism_report
from utils import init_session_state

# --- 全局配置 ---
CONFIG_DIR = "exam_configs"
PLAGIARISM_DIR = "plagiarism_data"
RESULTS_DIR = "exam_results"
REFLECTIONS_DIR = "student_reflections"
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(PLAGIARISM_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(REFLECTIONS_DIR, exist_ok=True)

if __name__ == "__main__":
    init_session_state()
    st.sidebar.title("导航")

    st.sidebar.subheader("AI API密钥设置")
    api_key = st.sidebar.text_input("输入AI API密钥", type="password",
                                    value=st.session_state.get('api_key', ''),
                                    help="从阿里云DashScope平台获取")
    st.session_state.api_key = api_key

    app_mode = st.sidebar.selectbox("选择模式", ["评分界面", "创建评分配置", "学情反馈", "抄袭情况", "心得体会分析"])

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
    elif app_mode == "心得体会分析":
        from reflection_analysis import show_reflection_analysis
        show_reflection_analysis()