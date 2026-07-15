"""
第 1 层(续)：实例数据 (ABox) —— 正经的知识图谱规模
=====================================================
Smart Campus 场景的完整实例数据。

规模: 6 院系 · 8 专业 · 12 教授 · 18 课程 · 12 技能 · 6 职业 · 8 学生
覆盖: 组织结构、课程先修链(多级)、技能传授、专业→职业映射、
      学生学习记录(含进行中/计划中课程)、技能等级
"""
from __future__ import annotations

from ontology import KnowledgeGraph


def build_knowledge_base() -> KnowledgeGraph:
    kg = KnowledgeGraph()

    # ========================================================== #
    # 1. 院系 Department (6)
    # ========================================================== #
    depts = [
        ("dept:cs",   "CS",   "计算机学院"),
        ("dept:ai",   "AI",   "人工智能学院"),
        ("dept:math", "MATH", "数学学院"),
        ("dept:ee",   "EE",   "电子工程学院"),
        ("dept:bus",  "BUS",  "商学院"),
        ("dept:des",  "DES",  "创意设计学院"),
    ]
    for eid, code, name in depts:
        kg.add_entity(eid, "Department", code=code, name=name)

    # ========================================================== #
    # 2. 专业 Major (8)  +  major_in_dept
    # ========================================================== #
    majors = [
        ("major:cs",   "CS",   "计算机科学与技术", "Bachelor", "dept:cs"),
        ("major:se",   "SE",   "软件工程",         "Bachelor", "dept:cs"),
        ("major:ds",   "DS",   "数据科学",         "Bachelor", "dept:ai"),
        ("major:ai",   "AI",   "人工智能",         "Bachelor", "dept:ai"),
        ("major:ee",   "EE",   "电子信息工程",     "Bachelor", "dept:ee"),
        ("major:math", "MATH", "应用数学",         "Bachelor", "dept:math"),
        ("major:stat", "STAT", "统计学",           "Bachelor", "dept:math"),
        ("major:fin",  "FIN",  "金融学",           "Bachelor", "dept:bus"),
    ]
    for eid, code, name, degree, dept in majors:
        kg.add_entity(eid, "Major", code=code, name=name, degree=degree)
        kg.add_relation(eid, "major_in_dept", dept)

    # ========================================================== #
    # 3. 教授 Professor (12)  +  belongs_to
    # ========================================================== #
    profs = [
        ("prof:wang",   "P001", "王教授", "Professor",       "机器学习",     "dept:cs"),
        ("prof:li",     "P002", "李教授", "Associate Prof",   "算法理论",     "dept:cs"),
        ("prof:sun",    "P003", "孙教授", "Professor",        "软件工程",     "dept:cs"),
        ("prof:zeng",   "P004", "曾教授", "Associate Prof",   "数据库系统",   "dept:cs"),
        ("prof:liu",    "P005", "刘教授", "Professor",        "深度学习",     "dept:ai"),
        ("prof:wu",     "P006", "吴教授", "Associate Prof",   "自然语言处理", "dept:ai"),
        ("prof:zhang",  "P007", "张教授", "Professor",        "统计学",       "dept:math"),
        ("prof:huang",  "P008", "黄教授", "Lecturer",          "线性代数",     "dept:math"),
        ("prof:zhao",   "P009", "赵教授", "Professor",        "信号处理",     "dept:ee"),
        ("prof:yang",   "P010", "杨教授", "Associate Prof",   "嵌入式系统",   "dept:ee"),
        ("prof:chen",   "P011", "陈教授", "Professor",        "金融工程",     "dept:bus"),
        ("prof:zhou",   "P012", "周教授", "Lecturer",          "数据分析",     "dept:bus"),
    ]
    for eid, pid, name, title, area, dept in profs:
        kg.add_entity(eid, "Professor", id=pid, name=name, title=title, research_area=area)
        kg.add_relation(eid, "belongs_to", dept)

    # ========================================================== #
    # 4. 技能 Skill (12)
    # ========================================================== #
    skills = [
        ("skill:python",  "Python编程",       "Programming"),
        ("skill:java",    "Java编程",         "Programming"),
        ("skill:algo",    "算法与数据结构",   "Programming"),
        ("skill:db",      "数据库系统",       "Programming"),
        ("skill:stat",    "概率统计",         "Math"),
        ("skill:linalg",  "线性代数",         "Math"),
        ("skill:discrete","离散数学",         "Math"),
        ("skill:ml",      "机器学习",         "AI"),
        ("skill:dl",      "深度学习",         "AI"),
        ("skill:nlp",     "自然语言处理",     "AI"),
        ("skill:viz",     "数据可视化",       "Soft"),
        ("skill:bigdata", "大数据技术",       "AI"),
    ]
    for eid, name, cat in skills:
        kg.add_entity(eid, "Skill", name=name, category=cat)

    # ========================================================== #
    # 5. 课程 Course (18)
    #    (eid, code, title, credits, difficulty, semester, dept, prof)
    # ========================================================== #
    courses = [
        # CS 基础
        ("course:cs101",  "CS101",  "程序设计基础",     3, 2, "Fall",   "dept:cs", "prof:li"),
        ("course:cs102",  "CS102",  "面向对象编程",     3, 2, "Spring", "dept:cs", "prof:sun"),
        # CS 核心
        ("course:cs201",  "CS201",  "数据结构与算法",   4, 3, "Spring", "dept:cs", "prof:li"),
        ("course:cs202",  "CS202",  "数据库系统",       3, 3, "Fall",   "dept:cs", "prof:zeng"),
        ("course:cs301",  "CS301",  "算法设计",         4, 4, "Fall",   "dept:cs", "prof:li"),
        ("course:cs302",  "CS302",  "软件工程实践",     3, 3, "Spring", "dept:cs", "prof:sun"),
        ("course:cs401",  "CS401",  "操作系统",         4, 4, "Fall",   "dept:cs", "prof:zeng"),
        # AI / ML
        ("course:ml401",  "ML401",  "机器学习",         4, 5, "Spring", "dept:ai", "prof:wang"),
        ("course:ml402",  "ML402",  "深度学习",         4, 5, "Fall",   "dept:ai", "prof:liu"),
        ("course:nlp401", "NLP401", "自然语言处理",     4, 4, "Spring", "dept:ai", "prof:wu"),
        # Math
        ("course:stat201","STAT201","概率论与统计",    3, 3, "Fall",   "dept:math","prof:zhang"),
        ("course:stat301","STAT301","应用统计",        3, 4, "Spring", "dept:math","prof:zhang"),
        ("course:math201","MATH201","线性代数",        3, 3, "Fall",   "dept:math","prof:huang"),
        ("course:math301","MATH301","离散数学",        3, 3, "Spring", "dept:math","prof:huang"),
        # DS
        ("course:ds301",  "DS301",  "数据可视化",       3, 2, "Spring", "dept:ai", "prof:wang"),
        ("course:ds401",  "DS401",  "大数据技术",       4, 4, "Fall",   "dept:ai", "prof:zhou"),
        # EE
        ("course:ee201",  "EE201",  "信号与系统",       3, 3, "Fall",   "dept:ee", "prof:zhao"),
        ("course:ee301",  "EE301",  "数字图像处理",     4, 4, "Spring", "dept:ee", "prof:yang"),
    ]
    for eid, code, title, cr, diff, sem, dept, prof in courses:
        kg.add_entity(eid, "Course", code=code, title=title, credits=cr,
                      difficulty=diff, semester=sem)
        kg.add_relation(eid, "offered_by", dept)
        kg.add_relation(eid, "taught_by", prof)
        kg.add_relation(prof, "teaches", eid)

    # ---- 先修链 prerequisite_of (A prerequisite_of B = A 是 B 的先修) ---- #
    prereqs = [
        ("course:cs101",  "course:cs102"),
        ("course:cs101",  "course:cs201"),
        ("course:cs201",  "course:cs301"),
        ("course:cs201",  "course:cs202"),
        ("course:cs201",  "course:ml401"),
        ("course:cs202",  "course:cs401"),
        ("course:cs301",  "course:cs401"),
        ("course:stat201","course:ml401"),
        ("course:math201","course:ml401"),
        ("course:ml401",  "course:ml402"),
        ("course:ml401",  "course:nlp401"),
        ("course:stat201","course:stat301"),
        ("course:math201","course:ee201"),
        ("course:ee201",  "course:ee301"),
        ("course:cs201",  "course:ds401"),
        ("course:cs101",  "course:ds301"),
        ("course:math201","course:math301"),
    ]
    for pre, post in prereqs:
        kg.add_relation(pre, "prerequisite_of", post)

    # ---- 课程传授技能 teaches_skill ---- #
    teaches_skill_map = {
        "course:cs101":  ["skill:python"],
        "course:cs102":  ["skill:java"],
        "course:cs201":  ["skill:algo", "skill:python"],
        "course:cs202":  ["skill:db"],
        "course:cs301":  ["skill:algo"],
        "course:cs302":  ["skill:java"],
        "course:cs401":  ["skill:db"],
        "course:ml401":  ["skill:ml", "skill:python"],
        "course:ml402":  ["skill:dl", "skill:ml"],
        "course:nlp401": ["skill:nlp", "skill:dl"],
        "course:stat201":["skill:stat"],
        "course:stat301":["skill:stat", "skill:viz"],
        "course:math201":["skill:linalg"],
        "course:math301":["skill:discrete"],
        "course:ds301":  ["skill:viz", "skill:python"],
        "course:ds401":  ["skill:bigdata", "skill:python"],
        "course:ee201":  ["skill:linalg"],
        "course:ee301":  ["skill:ml"],
    }
    for cid, sks in teaches_skill_map.items():
        for sk in sks:
            kg.add_relation(cid, "teaches_skill", sk)

    # ========================================================== #
    # 6. 职业方向 Career (6)  +  requires_skill
    # ========================================================== #
    careers = [
        ("career:swe", "软件工程师",     "互联网",     "20-40k/月", "高"),
        ("career:ds",  "数据科学家",     "互联网/AI",  "25-50k/月", "很高"),
        ("career:mle", "机器学习工程师", "AI",         "30-60k/月", "很高"),
        ("career:nle", "NLP工程师",      "AI",         "28-55k/月", "很高"),
        ("career:dba", "数据库工程师",   "互联网",     "18-35k/月", "中"),
        ("career:da",  "数据分析师",     "金融/互联网", "20-40k/月", "高"),
    ]
    for eid, name, field, salary, growth in careers:
        kg.add_entity(eid, "Career", name=name, field=field,
                      avg_salary=salary, growth_rate=growth)

    career_skills = {
        "career:swe": ["skill:python", "skill:algo", "skill:db"],
        "career:ds":  ["skill:python", "skill:stat", "skill:viz", "skill:ml"],
        "career:mle": ["skill:python", "skill:algo", "skill:linalg", "skill:ml", "skill:dl"],
        "career:nle": ["skill:python", "skill:algo", "skill:dl", "skill:nlp"],
        "career:dba": ["skill:db", "skill:algo", "skill:python"],
        "career:da":  ["skill:stat", "skill:viz", "skill:python", "skill:bigdata"],
    }
    for cid, sks in career_skills.items():
        for sk in sks:
            kg.add_relation(cid, "requires_skill", sk)

    # ========================================================== #
    # 7. 专业 → 必修课 requires_course  /  专业 → 职业 leads_to
    # ========================================================== #
    # 计算机科学与技术
    for c in ["course:cs101","course:cs102","course:cs201","course:cs202",
              "course:cs301","course:cs401","course:ml401"]:
        kg.add_relation("major:cs", "requires_course", c)
    kg.add_relation("major:cs", "leads_to", "career:swe")
    kg.add_relation("major:cs", "leads_to", "career:mle")

    # 软件工程
    for c in ["course:cs101","course:cs102","course:cs201","course:cs302","course:cs401"]:
        kg.add_relation("major:se", "requires_course", c)
    kg.add_relation("major:se", "leads_to", "career:swe")
    kg.add_relation("major:se", "leads_to", "career:dba")

    # 数据科学
    for c in ["course:cs101","course:cs201","course:stat201","course:math201",
              "course:ml401","course:ds301","course:ds401"]:
        kg.add_relation("major:ds", "requires_course", c)
    kg.add_relation("major:ds", "leads_to", "career:ds")
    kg.add_relation("major:ds", "leads_to", "career:da")

    # 人工智能
    for c in ["course:cs101","course:cs201","course:math201","course:stat201",
              "course:ml401","course:ml402","course:nlp401"]:
        kg.add_relation("major:ai", "requires_course", c)
    kg.add_relation("major:ai", "leads_to", "career:mle")
    kg.add_relation("major:ai", "leads_to", "career:nle")

    # 电子信息工程
    for c in ["course:cs101","course:math201","course:ee201","course:ee301"]:
        kg.add_relation("major:ee", "requires_course", c)
    kg.add_relation("major:ee", "leads_to", "career:swe")

    # 应用数学
    for c in ["course:math201","course:math301","course:stat201"]:
        kg.add_relation("major:math", "requires_course", c)
    kg.add_relation("major:math", "leads_to", "career:ds")

    # 统计学
    for c in ["course:stat201","course:stat301","course:math201","course:ds301"]:
        kg.add_relation("major:stat", "requires_course", c)
    kg.add_relation("major:stat", "leads_to", "career:da")
    kg.add_relation("major:stat", "leads_to", "career:ds")

    # 金融学
    for c in ["course:stat201","course:stat301"]:
        kg.add_relation("major:fin", "requires_course", c)
    kg.add_relation("major:fin", "leads_to", "career:da")

    # ========================================================== #
    # 8. 学生 Student (8) + 学习记录
    # ========================================================== #
    students = [
        # (eid, sid, name, grade, gpa, major, targets_career)
        ("student:alice", "S001", "Alice", 2024, 3.7, "major:cs", "career:mle"),
        ("student:bob",   "S002", "Bob",   2025, 3.5, "major:ds", "career:ds"),
        ("student:carol", "S003", "Carol", 2023, 3.8, "major:cs", "career:ds"),
        ("student:dave",  "S004", "Dave",  2024, 3.6, "major:se", "career:swe"),
        ("student:eve",   "S005", "Eve",   2023, 3.9, "major:ai", "career:mle"),
        ("student:frank", "S006", "Frank", 2025, 3.3, "major:ee", "career:swe"),
        ("student:grace", "S007", "Grace", 2024, 3.7, "major:stat", "career:da"),
        ("student:henry", "S008", "Henry", 2023, 3.4, "major:fin", "career:da"),
    ]

    # 每个学生的选课记录: (course, grade, status)
    student_records = {
        "student:alice": [
            ("course:cs101",  "A",  "passed"),
            ("course:cs102",  "A-", "passed"),
            ("course:cs201",  "B+", "passed"),
            ("course:stat201","B",  "passed"),
            ("course:ml401",  "B+", "ongoing"),
        ],
        "student:bob": [
            ("course:cs101",  "A",  "passed"),
            ("course:math201","B+", "passed"),
            ("course:stat201","B",  "passed"),
            ("course:ds301",  "A-", "ongoing"),
        ],
        "student:carol": [
            ("course:cs101",  "A",  "passed"),
            ("course:cs201",  "A",  "passed"),
            ("course:cs301",  "A-", "passed"),
            ("course:cs202",  "B+", "passed"),
        ],
        "student:dave": [
            ("course:cs101",  "B+", "passed"),
            ("course:cs102",  "A",  "passed"),
            ("course:cs201",  "B",  "passed"),
            ("course:cs302",  "A-", "ongoing"),
        ],
        "student:eve": [
            ("course:cs101",  "A",  "passed"),
            ("course:cs201",  "A",  "passed"),
            ("course:math201","A-", "passed"),
            ("course:stat201","A",  "passed"),
            ("course:ml401",  "A",  "passed"),
            ("course:ml402",  "A-", "ongoing"),
        ],
        "student:frank": [
            ("course:cs101",  "B",  "passed"),
            ("course:math201","B+", "passed"),
            ("course:ee201",  "B",  "ongoing"),
        ],
        "student:grace": [
            ("course:stat201","A",  "passed"),
            ("course:math201","A-", "passed"),
            ("course:stat301","B+", "passed"),
            ("course:ds301",  "A",  "passed"),
            ("course:ds401",  "B+", "ongoing"),
        ],
        "student:henry": [
            ("course:stat201","B+", "passed"),
            ("course:stat301","B",  "ongoing"),
        ],
    }

    # 每个学生的技能等级
    student_skills = {
        "student:alice": [("skill:python",4),("skill:algo",3),("skill:stat",2)],
        "student:bob":   [("skill:python",3),("skill:linalg",3),("skill:stat",2)],
        "student:carol": [("skill:python",4),("skill:algo",4),("skill:db",2)],
        "student:dave":  [("skill:python",3),("skill:java",4),("skill:algo",2)],
        "student:eve":   [("skill:python",5),("skill:algo",4),("skill:linalg",4),
                          ("skill:ml",4),("skill:stat",3)],
        "student:frank": [("skill:python",2),("skill:linalg",2)],
        "student:grace": [("skill:python",3),("skill:stat",4),("skill:viz",3)],
        "student:henry": [("skill:stat",3),("skill:python",2)],
    }

    for eid, sid, name, grade, gpa, major, target in students:
        kg.add_entity(eid, "Student", id=sid, name=name, grade=grade, gpa=gpa)
        kg.add_relation(eid, "enrolled_in", major)
        kg.add_relation(eid, "targets_career", target)
        for cid, g, status in student_records[eid]:
            kg.add_relation(eid, "takes", cid, grade=g, status=status)
        for sk, level in student_skills[eid]:
            kg.add_relation(eid, "has_skill", sk, level=level)

    return kg


if __name__ == "__main__":
    kg = build_knowledge_base()
    print(f"知识图谱: {kg}")
    print(f"统计: {kg.stats()}")
    from collections import Counter
    dist = Counter(e.etype for e in kg.list_entities())
    print("实体分布:", dict(dist))
    print(f"关系类型数: 见 ontology.RELATION_SCHEMAS")
