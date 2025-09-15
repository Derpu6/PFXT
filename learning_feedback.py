# learning_feedback.py
import streamlit as st
import os
import json
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime
import re

# 添加全局目录定义
REFLECTIONS_DIR = "student_reflections"
RESULTS_DIR = "exam_results"


def extract_emotion_score(analysis_text):
    """从分析文本中提取情绪评分"""
    emotion_pattern = r'情绪状态:\s*(\d+)/10'
    match = re.search(emotion_pattern, analysis_text)
    if match:
        return int(match.group(1))
    return 5  # 默认值


def extract_motivation_score(analysis_text):
    """从分析文本中提取动机评分"""
    motivation_pattern = r'学习动机:\s*(\d+)/10'
    match = re.search(motivation_pattern, analysis_text)
    if match:
        return int(match.group(1))
    return 5  # 默认值


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

    # 心得体会概览
    st.subheader("心得体会概览")
    if os.path.exists(REFLECTIONS_DIR):
        reflection_files = [f for f in os.listdir(REFLECTIONS_DIR) if f.endswith(".json") and exam_name in f]
        if reflection_files:
            st.write(f"已收集 {len(reflection_files)} 份心得体会")

            # 提取情绪和动机数据
            emotion_scores = []
            motivation_scores = []
            for file in reflection_files:
                filepath = os.path.join(REFLECTIONS_DIR, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    analysis = data.get('reflection_analysis', '')

                    emotion_score = extract_emotion_score(analysis)
                    motivation_score = extract_motivation_score(analysis)

                    emotion_scores.append(emotion_score)
                    motivation_scores.append(motivation_score)

            if emotion_scores and motivation_scores:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("平均情绪", f"{np.mean(emotion_scores):.1f}/10")
                with col2:
                    st.metric("平均动机", f"{np.mean(motivation_scores):.1f}/10")
        else:
            st.info("暂无心得体会数据")
    else:
        st.info("心得体会功能未启用")