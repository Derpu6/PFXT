# reflection_analysis.py
import streamlit as st
import os
import json
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime
import re

REFLECTIONS_DIR = "student_reflections"


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


def show_reflection_analysis():
    """显示心得体会分析界面"""
    st.header("📊 心得体会分析")

    # 获取所有心得体会文件
    reflection_files = [f for f in os.listdir(REFLECTIONS_DIR) if f.endswith(".json")]
    if not reflection_files:
        st.warning("没有找到任何心得体会数据")
        return

    # 按考试分组
    exams = {}
    for file in reflection_files:
        filepath = os.path.join(REFLECTIONS_DIR, file)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            exam_name = data['exam_name']
            if exam_name not in exams:
                exams[exam_name] = []
            exams[exam_name].append(data)

    selected_exam = st.selectbox("选择考试", list(exams.keys()))

    if selected_exam:
        st.subheader(f"考试: {selected_exam}")
        reflections = exams[selected_exam]

        # 显示情绪和动机趋势
        st.subheader("学生情绪与动机趋势")

        emotion_data = []
        motivation_data = []
        for reflection in reflections:
            emotion_score = extract_emotion_score(reflection.get('reflection_analysis', ''))
            motivation_score = extract_motivation_score(reflection.get('reflection_analysis', ''))

            emotion_data.append({
                'student': f"{reflection['student_id']}_{reflection['student_name']}",
                'score': emotion_score,
                'type': '情绪'
            })

            motivation_data.append({
                'student': f"{reflection['student_id']}_{reflection['student_name']}",
                'score': motivation_score,
                'type': '动机'
            })

        # 创建图表数据
        chart_data = pd.DataFrame(emotion_data + motivation_data)

        if not chart_data.empty:
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('student:N', title='学生', sort=None),
                y=alt.Y('score:Q', title='评分', scale=alt.Scale(domain=[0, 10])),
                color=alt.Color('type:N', legend=alt.Legend(title="类型")),
                column=alt.Column('type:N', header=alt.Header(title=""))
            ).properties(width=200, height=300)

            st.altair_chart(chart)

        # 显示详细分析
        st.subheader("详细分析")
        for reflection in reflections:
            with st.expander(f"{reflection['student_id']} - {reflection['student_name']}"):
                col1, col2 = st.columns(2)
                with col1:
                    emotion_score = extract_emotion_score(reflection.get('reflection_analysis', ''))
                    st.metric("情绪评分", f"{emotion_score}/10")
                with col2:
                    motivation_score = extract_motivation_score(reflection.get('reflection_analysis', ''))
                    st.metric("动机评分", f"{motivation_score}/10")

                st.write("心得体会内容:")
                st.text_area("", value=reflection.get('reflection_content', ''), height=150,
                             key=f"content_{reflection['student_id']}")

                st.write("AI分析结果:")
                st.text_area("", value=reflection.get('reflection_analysis', ''), height=200,
                             key=f"analysis_{reflection['student_id']}")

        # 学习体验曲线
        st.subheader("学习体验曲线")

        # 按时间排序
        sorted_reflections = sorted(reflections, key=lambda x: x.get('reflection_date', ''))

        timeline_data = []
        for i, reflection in enumerate(sorted_reflections):
            emotion_score = extract_emotion_score(reflection.get('reflection_analysis', ''))
            motivation_score = extract_motivation_score(reflection.get('reflection_analysis', ''))

            timeline_data.append({
                '顺序': i + 1,
                '学生': f"{reflection['student_id']}_{reflection['student_name']}",
                '情绪': emotion_score,
                '动机': motivation_score
            })

        timeline_df = pd.DataFrame(timeline_data)

        if not timeline_df.empty:
            # 情绪曲线
            emotion_chart = alt.Chart(timeline_df).mark_line(point=True).encode(
                x=alt.X('顺序:Q', title='提交顺序'),
                y=alt.Y('情绪:Q', title='情绪评分', scale=alt.Scale(domain=[0, 10])),
                color=alt.value('blue'),
                tooltip=['学生', '情绪']
            ).properties(width=600, height=300)

            # 动机曲线
            motivation_chart = alt.Chart(timeline_df).mark_line(point=True).encode(
                x=alt.X('顺序:Q', title='提交顺序'),
                y=alt.Y('动机:Q', title='动机评分', scale=alt.Scale(domain=[0, 10])),
                color=alt.value('green'),
                tooltip=['学生', '动机']
            ).properties(width=600, height=300)

            st.altair_chart(emotion_chart)
            st.altair_chart(motivation_chart)

            # 综合体验指数
            timeline_df['体验指数'] = (timeline_df['情绪'] + timeline_df['动机']) / 2
            experience_chart = alt.Chart(timeline_df).mark_line(point=True, color='red').encode(
                x=alt.X('顺序:Q', title='提交顺序'),
                y=alt.Y('体验指数:Q', title='体验指数', scale=alt.Scale(domain=[0, 10])),
                tooltip=['学生', '体验指数']
            ).properties(width=600, height=300)

            st.altair_chart(experience_chart)

            # 显示统计信息
            avg_emotion = timeline_df['情绪'].mean()
            avg_motivation = timeline_df['动机'].mean()
            avg_experience = timeline_df['体验指数'].mean()

            col1, col2, col3 = st.columns(3)
            col1.metric("平均情绪", f"{avg_emotion:.1f}/10")
            col2.metric("平均动机", f"{avg_motivation:.1f}/10")
            col3.metric("平均体验", f"{avg_experience:.1f}/10")