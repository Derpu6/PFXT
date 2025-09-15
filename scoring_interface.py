# scoring_interface.py
import streamlit as st
import json
import os
import datetime
import pandas as pd
import numpy as np
import altair as alt
from docx import Document
import re
from ai_integration import ai_assistant_score, ai_analyze_reflection
from code_analysis import analyze_code
from utils import save_results


def extract_from_docx(file):
    """从DOCX文件中提取代码和心得体会"""
    try:
        doc = Document(file)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)

        content = "\n".join(full_text)

        # 尝试通过常见分隔符分割代码和心得体会
        code_sections = []
        reflection_sections = []

        # 常见代码分隔符
        code_patterns = [
            r'代码部分[:：]?\s*(.*?)(?=心得体会|心得|总结|$)',
            r'程序代码[:：]?\s*(.*?)(?=心得体会|心得|总结|$)',
            r'源代码[:：]?\s*(.*?)(?=心得体会|心得|总结|$)'
        ]

        # 常见心得体会分隔符
        reflection_patterns = [
            r'心得体会[:：]?\s*(.*?)(?=代码部分|程序代码|源代码|$)',
            r'心得[:：]?\s*(.*?)(?=代码部分|程序代码|源代码|$)',
            r'总结[:：]?\s*(.*?)(?=代码部分|程序代码|源代码|$)'
        ]

        # 尝试提取代码
        code_content = ""
        for pattern in code_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                code_content = match.group(1).strip()
                break

        # 如果没找到特定模式，尝试通过内容特征识别
        if not code_content:
            # 查找可能包含代码的部分（有缩进、特殊字符等）
            lines = content.split('\n')
            code_lines = []
            in_code = False

            for line in lines:
                # 代码特征：包含缩进、括号、分号等
                if (re.search(r'^\s+', line) or
                        re.search(r'[{};()=<>]', line) or
                        re.search(r'(def|class|function|void|int|float|char|#include)', line)):
                    code_lines.append(line)
                    in_code = True
                elif in_code and line.strip() == '':
                    code_lines.append(line)
                elif in_code and not line.strip() == '':
                    break

            code_content = "\n".join(code_lines)

        # 尝试提取心得体会
        reflection_content = ""
        for pattern in reflection_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                reflection_content = match.group(1).strip()
                break

        # 如果没找到特定模式，假设剩余部分是心得体会
        if not reflection_content and code_content:
            reflection_content = content.replace(code_content, "").strip()
        elif not reflection_content:
            reflection_content = content

        return code_content, reflection_content
    except Exception as e:
        st.error(f"解析DOCX文件时出错: {str(e)}")
        return "", ""


def scoring_interface(config):
    """评分界面 - 支持DOCX文件"""
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

    st.subheader("作业提交")
    uploaded_file = st.file_uploader("上传学生作业", type=['c', 'cpp', 'h', 'py', 'docx'])
    code_content = st.session_state.get('student_code', "")
    reflection_content = st.session_state.get('reflection_content', "")

    if uploaded_file is not None:
        # 处理DOCX文件
        if uploaded_file.name.endswith('.docx'):
            with st.spinner("正在解析DOCX文件..."):
                code_content, reflection_content = extract_from_docx(uploaded_file)

                if code_content:
                    st.session_state.student_code = code_content
                    # 尝试识别语言
                    if re.search(r'(def|class|import|print\(|#!)', code_content):
                        language = 'python'
                    else:
                        language = 'c'
                    st.session_state.language = language

                    with st.expander("查看提取的代码", expanded=False):
                        if language == "python":
                            st.code(code_content, language="python")
                        else:
                            st.code(code_content, language="c")

                if reflection_content:
                    st.session_state.reflection_content = reflection_content
                    with st.expander("查看心得体会", expanded=False):
                        st.text_area("", value=reflection_content, height=200)
        else:
            # 处理代码文件
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
                # 语言识别
                if uploaded_file.name.endswith('.py'):
                    language = 'python'
                elif uploaded_file.name.endswith('.cpp') or uploaded_file.name.endswith('.h'):
                    language = 'cpp'
                else:
                    language = 'c'
                st.session_state.language = language

                with st.expander("查看代码", expanded=False):
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

    # 心得体会分析
    if reflection_content:
        st.subheader("心得体会分析")
        if st.button("🤖 AI分析心得体会", key="ai_reflection"):
            with st.spinner("AI正在分析心得体会..."):
                reflection_analysis = ai_analyze_reflection(
                    reflection_content,
                    st.session_state.api_key
                )
                st.session_state.reflection_analysis = reflection_analysis

        if 'reflection_analysis' in st.session_state:
            st.info(st.session_state.reflection_analysis)

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
                    st.session_state.language,
                    reflection_content,
                    st.session_state.get('reflection_analysis', "")
                )
                st.success(f"✅ 评分结果已保存至: {result_file}", icon="🎉")
            except Exception as e:
                st.error(f"❌ 保存评分结果时出错: {e}")
        else:
            st.warning("⚠️ 请填写学号和姓名后再提交。")