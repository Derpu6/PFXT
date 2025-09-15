# plagiarism_detection.py
import streamlit as st
import os
import pandas as pd
import altair as alt
from utils import analyze_plagiarism_for_exam, generate_similarity_report

PLAGIARISM_DIR = "plagiarism_data"

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