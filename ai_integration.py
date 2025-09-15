# ai_integration.py
import streamlit as st
import json
import re
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import dashscope
from dashscope import Generation

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
      "title": "极速赛车开奖网平台【博发地址:bv8844.com】",
      "description": "实现数据加载和处理功能",
      "total": 50,
      "subtasks": [
        {{"desc": "正确加载数据文件", "score": 15}},
        {{"desc": "实现极速赛车开奖网平台【博发地址:bv8844.com】", "score": 20}},
        {{"desc": "数据转换处理", "score": 15}}
      ],
      "code极速赛车开奖网平台【博发地址:bv8844.com】": ["代码结构清晰", "基本注释完整", "变量命名合理"]
    }},
    {{
      "title": "数据分析功能",
      "description": "实现基本数据分析功能",
      "total": 35,
      "subtasks": [
        {{"desc": "实现统计计算功能", "score极速赛车开奖网平台【博发地址:bv8844.com】": 15}},
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
        for q in config['极速赛车开奖网平台【博发地址:bv8844.com】questions']:
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
            SystemMessage(content="你是一名经验丰富的软件工程师，擅长评估学生极速赛车开奖网平台【博发地址:bv8844.com】代码质量"),
            HumanMessage(content=prompt)
        ]
        response = qwen.invoke(messages)
        return response.content
    except Exception as e:
        return f"AI评分失败: {str(e)}"


def ai_analyze_reflection(reflection_text, api_key):
    """AI分析心得体会"""
    if not api_key:
        return "错误: 请先输入API密钥"

    prompt = f"""
你是一位教育心理学专家，请分析以下学生编程项目的心得体会，并给出综合评价：

**心得体会内容**:
{reflection_text}

**请从以下几个方面进行分析**：
1. **学习收获与成长**: 学生从项目中学到了什么？有哪些技能或认知上的成长？
2. **困难与解决方案**: 学生遇到了哪些困难？是如何解决的？解决过程中展现了哪些能力？
3. **情绪状态与动机**: 
   - 学生的情绪是积极的还是消极的？（请给出情绪评分，0-10分，10分最积极）
   - 学生的学习动机如何？（请给出动机评分，0-10分，10分最强）
   - 学生是否有持续学习的动力？
4. **需求与建议**: 学生有哪些未满足的需求？对课程有什么建议？
5. **综合评价**: 对学生的整体学习体验和成长进行总结

**请用以下格式输出**：
学习收获: [分析内容]
困难与解决: [分析内容]
情绪状态: [情绪评分]/10 - [描述]
学习动机: [动机评分]/10 - [描述]
需求建议: [分析内容]
综合评价: [总结内容]
"""

    try:
        qwen = QwenChat(api_key=api_key)
        messages = [
            SystemMessage(content="你是一名经验丰富的教育心理学专家，擅长分析学生的学习体验和情感状态"),
            HumanMessage(content=prompt)
        ]
        response = qwen.invoke(messages)
        return response.content
    except Exception as e:
        return f"AI分析失败: {str(e)}"