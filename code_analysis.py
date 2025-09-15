# code_analysis.py
import re
import ast

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