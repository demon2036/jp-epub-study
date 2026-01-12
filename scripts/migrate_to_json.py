#!/usr/bin/env python3
"""迁移现有MD文件到JSON数据库"""
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
MD_DIR = DATA_DIR / "kanji_explanations"
GRADE_FILE = DATA_DIR / "kyoiku_kanji_2020_by_grade.json"
DB_FILE = DATA_DIR / "kanji_db.json"

def main():
    # 加载年级数据
    grade_data = json.loads(GRADE_FILE.read_text(encoding="utf-8"))

    # 构建汉字->年级映射
    kanji_to_grade = {}
    for grade, kanji_list in grade_data["by_grade"].items():
        for k in kanji_list:
            kanji_to_grade[k] = int(grade)

    # 读取现有MD文件
    kanji_db = {"meta": {"total": grade_data["total"], "completed": 0, "last_updated": datetime.now().isoformat()}, "kanji": {}}

    for md_file in MD_DIR.glob("*.md"):
        kanji = md_file.stem
        if kanji in kanji_to_grade:
            content = md_file.read_text(encoding="utf-8")
            kanji_db["kanji"][kanji] = {
                "grade": kanji_to_grade[kanji],
                "status": "completed",
                "content": content
            }
            kanji_db["meta"]["completed"] += 1

    # 添加未完成的汉字
    for kanji, grade in kanji_to_grade.items():
        if kanji not in kanji_db["kanji"]:
            kanji_db["kanji"][kanji] = {"grade": grade, "status": "pending", "content": None}

    DB_FILE.write_text(json.dumps(kanji_db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已创建: {DB_FILE}")
    print(f"完成: {kanji_db['meta']['completed']}/{kanji_db['meta']['total']}")

if __name__ == "__main__":
    main()
