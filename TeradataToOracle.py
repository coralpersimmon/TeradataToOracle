import csv
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import scrolledtext


BASE_DIR = Path(__file__).resolve().parent
RULES_FILE = BASE_DIR / "TTOrules.csv"


@dataclass
class ScanIssue:
    category: str
    line: int | None
    message: str


@dataclass
class Statement:
    text: str
    masked_text: str
    start_line: int
    first_keyword: str
    base_offset: int


root = tk.Tk()
root.title("TD → Oracle")
root.geometry("1200x800")


editor_frame = tk.Frame(root)
editor_frame.pack(fill="both", expand=True, padx=10, pady=10)

line_box = tk.Text(
    editor_frame,
    width=6,
    font=("Consolas", 12),
    bg="#f3f3f3",
    fg="#666666",
    state="disabled",
    wrap="none",
    takefocus=0,
    bd=0,
    padx=8,
)
line_box.pack(side="left", fill="y")

text_scrollbar = tk.Scrollbar(editor_frame)
text_scrollbar.pack(side="right", fill="y")

text_box = tk.Text(
    editor_frame,
    font=("Consolas", 12),
    bg="white",
    fg="black",
    insertbackground="black",
    wrap="none",
    undo=True,
    yscrollcommand=text_scrollbar.set,
)
text_box.pack(side="left", fill="both", expand=True)

cursor_label = tk.Label(root, anchor="w", font=("Consolas", 10), text="Ln 1, Col 1")
cursor_label.pack(fill="x", padx=10)

result_frame = tk.Frame(root)
result_frame.pack(fill="both", padx=10, pady=10)

syntax_frame = tk.LabelFrame(result_frame, text="Oracle語法違規")
syntax_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

ods_frame = tk.LabelFrame(result_frame, text="ODS規則相關違規")
ods_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))

syntax_result_box = scrolledtext.ScrolledText(
    syntax_frame,
    height=12,
    font=("Consolas", 11),
    bg="white",
    fg="black",
)
syntax_result_box.pack(fill="both", expand=True)

ods_result_box = scrolledtext.ScrolledText(
    ods_frame,
    height=12,
    font=("Consolas", 11),
    bg="white",
    fg="black",
)
ods_result_box.pack(fill="both", expand=True)

text_box.tag_config("error", foreground="red")
text_box.tag_config("bracket_error", background="red", foreground="white")
text_box.tag_config("line_error", foreground="red")

FUNCTION_LIKE_WORDS = [
    "ZEROIFNULL", "OREPLACE", "ISNULL", "POSITION", "CHAR_LENGTH",
    "CHARACTER_LENGTH", "SUM", "COUNT", "AVG", "MIN", "MAX", "NVL",
    "TRIM", "SUBSTR", "ROW_NUMBER",
]


def load_rules():
    rules = []
    if not RULES_FILE.exists():
        return rules

    with RULES_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            pattern = (row.get("pattern") or "").strip()
            message = (row.get("message") or "").strip()
            category = (row.get("category") or "syntax").strip().lower()
            source = (row.get("source") or "line").strip().lower()
            enabled = (row.get("enabled") or "Y").strip().upper()

            if not pattern or not message or enabled not in {"Y", "YES", "1", "TRUE"}:
                continue

            rules.append({
                "pattern": pattern,
                "message": message,
                "category": category,
                "source": source,
            })
    return rules


RULES = load_rules()


def sync_scroll(*args):
    text_box.yview(*args)
    line_box.yview(*args)


def on_text_scroll(first, last):
    text_scrollbar.set(first, last)
    line_box.yview_moveto(first)


text_scrollbar.config(command=lambda *args: sync_scroll(*args))


def clear_tags():
    for tag in ("error", "bracket_error", "line_error"):
        text_box.tag_remove(tag, "1.0", tk.END)


def update_line_numbers(event=None):
    line_count = int(text_box.index("end-1c").split(".")[0])
    line_text = "\n".join(str(i) for i in range(1, line_count + 1))

    line_box.config(state="normal")
    line_box.delete("1.0", tk.END)
    line_box.insert("1.0", line_text)
    line_box.tag_add("line_numbers", "1.0", tk.END)
    line_box.config(state="disabled")
    line_box.yview_moveto(text_box.yview()[0])


def update_cursor_label(event=None):
    row, col = text_box.index("insert").split(".")
    cursor_label.config(text=f"Ln {row}, Col {int(col) + 1}")


def mask_preserve_length(sql: str) -> str:
    chars = list(sql)
    i = 0
    length = len(chars)

    while i < length:
        if chars[i:i + 2] == ["-", "-"]:
            j = i
            while j < length and chars[j] != "\n":
                chars[j] = " "
                j += 1
            i = j
            continue

        if chars[i:i + 2] == ["/", "*"]:
            chars[i] = " "
            if i + 1 < length:
                chars[i + 1] = " "
            j = i + 2
            while j < length - 1:
                if chars[j:j + 2] == ["*", "/"]:
                    chars[j] = " "
                    chars[j + 1] = " "
                    j += 2
                    break
                if chars[j] != "\n":
                    chars[j] = " "
                j += 1
            i = j
            continue

        if chars[i] == "'":
            chars[i] = " "
            j = i + 1
            while j < length:
                if chars[j] == "'":
                    chars[j] = " "
                    if j + 1 < length and chars[j + 1] == "'":
                        chars[j + 1] = " "
                        j += 2
                        continue
                    j += 1
                    break
                if chars[j] != "\n":
                    chars[j] = " "
                j += 1
            i = j
            continue

        i += 1

    return "".join(chars)


def split_statements(sql: str, masked_sql: str):
    statements = []
    start = 0

    for match in re.finditer(r";", masked_sql):
        end = match.start()
        raw_chunk = sql[start:end]
        raw_masked_chunk = masked_sql[start:end]
        if raw_chunk.strip():
            content_match = re.search(r"\S", raw_masked_chunk)
            if not content_match:
                start = match.end()
                continue

            content_start = content_match.start()
            chunk = raw_chunk[content_start:].rstrip()
            masked_chunk = raw_masked_chunk[content_start:].rstrip()
            chunk_start = start + content_start
            start_line = masked_sql.count("\n", 0, chunk_start) + 1
            keyword_match = re.search(r"\b([A-Z]+)\b", masked_chunk, re.IGNORECASE)
            first_keyword = keyword_match.group(1).upper() if keyword_match else ""
            statements.append(Statement(chunk, masked_chunk, start_line, first_keyword, chunk_start))
        start = match.end()

    raw_tail = sql[start:]
    raw_masked_tail = masked_sql[start:]
    if raw_tail.strip():
        content_match = re.search(r"\S", raw_masked_tail)
        if not content_match:
            return statements

        content_start = content_match.start()
        tail = raw_tail[content_start:].rstrip()
        masked_tail = raw_masked_tail[content_start:].rstrip()
        tail_start = start + content_start
        start_line = masked_sql.count("\n", 0, tail_start) + 1
        keyword_match = re.search(r"\b([A-Z]+)\b", masked_tail, re.IGNORECASE)
        first_keyword = keyword_match.group(1).upper() if keyword_match else ""
        statements.append(Statement(tail, masked_tail, start_line, first_keyword, tail_start))

    return statements


def add_issue(issues, line_no, message, category):
    issues.append(ScanIssue(category=category, line=line_no, message=message))


def add_tag(line_no, start_col, end_col, tag="error"):
    if tag == "line_error":
        raw_line = text_box.get(f"{line_no}.0", f"{line_no}.end")
        highlight_end = len(raw_line)

        for marker in ("--", "/*"):
            marker_index = raw_line.find(marker)
            if marker_index != -1:
                highlight_end = min(highlight_end, marker_index)

        if raw_line.strip().startswith("--") or raw_line.strip().startswith("/*"):
            return

        if highlight_end <= 0:
            return

        text_box.tag_add(tag, f"{line_no}.0", f"{line_no}.{highlight_end}")
    else:
        text_box.tag_add(tag, f"{line_no}.{start_col}", f"{line_no}.{end_col}")


def absolute_line(statement: Statement, offset: int) -> int:
    return statement.start_line + statement.masked_text.count("\n", 0, offset)


def statement_line_col(statement: Statement, offset: int):
    line_no = absolute_line(statement, offset)
    line_start = statement.masked_text.rfind("\n", 0, offset) + 1
    start_col = offset - line_start
    return line_no, start_col


def mark_issue_lines(issues):
    marked_lines = sorted({item.line for item in issues if item.line is not None})
    for line_no in marked_lines:
        add_tag(line_no, 0, 0, "line_error")


def run_rule_file(sql, masked_sql, issues):
    source_map = {
        "sql": sql,
        "masked_sql": masked_sql,
    }

    for rule in RULES:
        content = source_map.get(rule["source"])
        if content is None:
            continue

        for match in re.finditer(rule["pattern"], content, re.IGNORECASE | re.MULTILINE):
            line_no = content.count("\n", 0, match.start()) + 1
            line_start = content.rfind("\n", 0, match.start()) + 1
            add_tag(line_no, match.start() - line_start, match.end() - line_start)
            add_issue(issues, line_no, rule["message"], rule["category"])


def check_parentheses(masked_sql, issues):
    stack = []
    lines = masked_sql.split("\n")

    for line_no, line in enumerate(lines, start=1):
        for col_no, char in enumerate(line):
            if char == "(":
                stack.append((line_no, col_no))
            elif char == ")":
                if stack:
                    stack.pop()
                else:
                    add_tag(line_no, col_no, col_no + 1, "bracket_error")
                    add_issue(issues, line_no, "多餘右括號 )", "syntax")

    for line_no, col_no in stack:
        add_tag(line_no, col_no, col_no + 1, "bracket_error")
        add_issue(issues, line_no, "缺少右括號 )", "syntax")


def check_case_end(masked_sql, issues):
    case_count = len(re.findall(r"\bCASE\b", masked_sql, re.IGNORECASE))
    end_count = len(re.findall(r"\bEND\b", masked_sql, re.IGNORECASE))
    if case_count != end_count:
        add_issue(
            issues,
            None,
            f"CASE/END 數量不一致，CASE={case_count} END={end_count}",
            "syntax",
        )


def check_common_structure(masked_sql, issues):
    for match in re.finditer(r",\s*FROM\b", masked_sql, re.IGNORECASE):
        line_no = masked_sql.count("\n", 0, match.start()) + 1
        add_tag(line_no, 0, 1)
        add_issue(issues, line_no, "SELECT 欄位尾端可能多了一個逗號", "syntax")

    for match in re.finditer(r"\bIN\s*\(\s*\)", masked_sql, re.IGNORECASE):
        line_no = masked_sql.count("\n", 0, match.start()) + 1
        add_issue(issues, line_no, "發現空的 IN ()，Oracle 會報錯", "syntax")

    for match in re.finditer(r",\s*,", masked_sql):
        line_no = masked_sql.count("\n", 0, match.start()) + 1
        add_issue(issues, line_no, "連續逗號，欄位清單可能有缺值", "syntax")


def check_primary_index_context(statements, issues):
    pattern = re.compile(r"\b(?:UNIQUE\s+)?PRIMARY\s+INDEX\s*\(", re.IGNORECASE)
    for statement in statements:
        for match in pattern.finditer(statement.masked_text):
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues,
                line_no,
                "Teradata PRIMARY INDEX 語法，Oracle 不支援",
                "syntax",
            )


def check_index_function(statements, issues):
    pattern = re.compile(r"\bINDEX\s*\(", re.IGNORECASE)
    for statement in statements:
        for match in pattern.finditer(statement.masked_text):
            prefix = statement.masked_text[max(0, match.start() - 25):match.start()].upper()
            if re.search(r"(?:UNIQUE\s+)?PRIMARY\s+$", prefix):
                continue
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues,
                line_no,
                "Oracle 沒有 INDEX() 字串函式 -> INSTR()",
                "syntax",
            )


def check_function_parentheses(masked_sql, issues):
    lines = masked_sql.split("\n")
    for line_no, line in enumerate(lines, start=1):
        for func in FUNCTION_LIKE_WORDS:
            pattern = rf"\b{func}\b\s+(?!\()(?=[A-Z0-9_\"'])"
            for match in re.finditer(pattern, line, re.IGNORECASE):
                add_tag(line_no, match.start(), match.end())
                add_issue(
                    issues,
                    line_no,
                    f"{func} 後面建議補上括號",
                    "syntax",
                )


def check_qualify_conversion(statements, issues):
    pattern = re.compile(r"\bQUALIFY\s+ROW_NUMBER\s*\(", re.IGNORECASE)
    for statement in statements:
        for match in pattern.finditer(statement.masked_text):
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len("QUALIFY"))
            add_issue(
                issues,
                line_no,
                "Oracle 不支援 QUALIFY -> 子查詢 + ROW_NUMBER() + WHERE RN = 1",
                "syntax",
            )


def check_generic_qualify(statements, issues):
    pattern = re.compile(r"\bQUALIFY\b", re.IGNORECASE)
    for statement in statements:
        if re.search(r"\bQUALIFY\s+ROW_NUMBER\s*\(", statement.masked_text, re.IGNORECASE):
            continue

        for match in pattern.finditer(statement.masked_text):
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues,
                line_no,
                "Oracle 不支援 QUALIFY",
                "syntax",
            )


def check_format_conversion(statements, issues):
    date_pattern = re.compile(r"\bDATE\s+FORMAT\s+'([^']+)'", re.IGNORECASE)
    timestamp_pattern = re.compile(r"\bTIMESTAMP\s+FORMAT\s+'([^']+)'", re.IGNORECASE)
    generic_pattern = re.compile(r"\bFORMAT\s+'([^']+)'", re.IGNORECASE)

    for statement in statements:
        seen_ranges = []

        for pattern, builder in [
            (date_pattern, lambda fmt: "DATE FORMAT -> Date"),
            (timestamp_pattern, lambda fmt: "TIMESTAMP FORMAT -> Timestamp"),
            (generic_pattern, lambda fmt: "FORMAT -> Char"),
        ]:
            for match in pattern.finditer(statement.text):
                if any(start <= match.start() < end for start, end in seen_ranges):
                    continue
                seen_ranges.append((match.start(), match.end()))
                line_no, start_col = statement_line_col(statement, match.start())
                add_tag(line_no, start_col, start_col + len(match.group(0)))
                add_issue(
                    issues,
                    line_no,
                    builder(match.group(1)),
                    "syntax",
            )


def check_inline_view_alias(statements, issues):
    for statement in statements:
        for match in re.finditer(r"\b(?:FROM|JOIN)\s*\(\s*SELECT\b", statement.masked_text, re.IGNORECASE):
            tail = statement.masked_text[match.end():match.end() + 500]
            alias_needed = re.search(r"\)\s*(WHERE|GROUP\s+BY|ORDER\s+BY|UNION|JOIN|ON|$)", tail, re.IGNORECASE)
            if alias_needed:
                line_no, start_col = statement_line_col(statement, match.start())
                add_tag(line_no, start_col, start_col + len(match.group(0)))
                add_issue(
                    issues,
                    line_no,
                    "子查詢後面可能缺少別名，Oracle inline view 建議補上 alias",
                    "syntax",
            )


def check_ods_delete(statements, issues):
    pattern = re.compile(r"^\s*DELETE\b", re.IGNORECASE)
    for statement in statements:
        match = pattern.search(statement.masked_text)
        if match:
            line_no = statement.start_line
            add_issue(
                issues,
                line_no,
                "ODS 規範建議：DELETE 改為 Working Table + RENAME",
                "ods",
            )


def check_ods_create_index_order(statements, issues):
    first_insert_index = next((i for i, stmt in enumerate(statements) if stmt.first_keyword == "INSERT"), None)
    if first_insert_index is None:
        return

    for i, statement in enumerate(statements):
        if statement.first_keyword == "CREATE" and re.search(r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", statement.masked_text, re.IGNORECASE):
            if i < first_insert_index:
                add_issue(
                    issues,
                    statement.start_line,
                    "ODS 規範建議：INSERT 完再 CREATE INDEX",
                    "ods",
                )


def check_ods_create_table_options(statements, issues):
    for statement in statements:
        if not re.search(r"^\s*CREATE\s+.*\bTABLE\b", statement.masked_text, re.IGNORECASE):
            continue

        upper_text = statement.masked_text.upper()
        if "NOLOGGING" not in upper_text:
            add_issue(
                issues,
                statement.start_line,
                "ODS 規範建議：TABLE 添加 NOLOGGING COMPRESS NOCACHE",
                "ods",
            )

 

def check_ods_partition_local_index(statements, issues):
    partition_tables = set()

    for statement in statements:
        create_table_match = re.search(
            r"^\s*CREATE\s+.*?\bTABLE\s+([A-Z0-9_.$]+)",
            statement.masked_text,
            re.IGNORECASE,
        )
        if create_table_match and "PARTITION" in statement.masked_text.upper():
            partition_tables.add(create_table_match.group(1).upper())

    if not partition_tables:
        return

    for statement in statements:
        index_match = re.search(
            r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+[A-Z0-9_.$]+\s+ON\s+([A-Z0-9_.$]+)",
            statement.masked_text,
            re.IGNORECASE,
        )
        if not index_match:
            continue

        table_name = index_match.group(1).upper()
        if table_name in partition_tables and " LOCAL" not in statement.masked_text.upper():
            add_issue(
                issues,
                statement.start_line,
                "ODS 分割表索引建議評估 LOCAL INDEX",
                "ods",
            )


def dedupe_issues(issues):
    seen = set()
    result = []
    for item in issues:
        key = (item.category, item.line, item.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def sort_issues(issues):
    return sorted(
        issues,
        key=lambda item: (
            item.line is None,
            item.line if item.line is not None else 999999,
            item.message,
        ),
    )


def render_results(issues):
    syntax_result_box.delete("1.0", tk.END)
    ods_result_box.delete("1.0", tk.END)

    syntax_issues = [item for item in issues if item.category == "syntax"]
    ods_issues = [item for item in issues if item.category == "ods"]

    if syntax_issues:
        lines = []
        for item in syntax_issues:
            if item.line is None:
                lines.append(item.message)
            else:
                lines.append(f"[Line {item.line:02d}]  {item.message}")
        syntax_result_box.insert(tk.END, "\n".join(lines))
    else:
        syntax_result_box.insert(tk.END, "未發現實際語法違規")

    if ods_issues:
        lines = []
        for item in ods_issues:
            if item.line is None:
                lines.append(item.message)
            else:
                lines.append(f"[Line {item.line:02d}]  {item.message}")
        ods_result_box.insert(tk.END, "\n".join(lines))
    else:
        ods_result_box.insert(tk.END, "未發現 ODS 規則違規")


def check_sql():
    clear_tags()

    sql = text_box.get("1.0", tk.END)
    masked_sql = mask_preserve_length(sql)
    statements = split_statements(sql, masked_sql)

    issues = []
    run_rule_file(sql, masked_sql, issues)
    check_parentheses(masked_sql, issues)
    check_case_end(masked_sql, issues)
    check_common_structure(masked_sql, issues)
    check_primary_index_context(statements, issues)
    check_index_function(statements, issues)
    check_function_parentheses(masked_sql, issues)
    check_generic_qualify(statements, issues)
    check_qualify_conversion(statements, issues)
    check_format_conversion(statements, issues)
    check_inline_view_alias(statements, issues)
    check_ods_delete(statements, issues)
    check_ods_create_index_order(statements, issues)
    check_ods_create_table_options(statements, issues)
    check_ods_partition_local_index(statements, issues)

    issues = sort_issues(dedupe_issues(issues))
    mark_issue_lines(issues)
    render_results(issues)


btn = tk.Button(
    root,
    text="執行檢查",
    font=("Microsoft JhengHei", 12),
    command=check_sql,
)
btn.pack(pady=5)


line_box.tag_configure("line_numbers", justify="right")
text_box.config(yscrollcommand=on_text_scroll)
text_box.bind("<KeyRelease>", update_line_numbers)
text_box.bind("<KeyRelease>", update_cursor_label, add="+")
text_box.bind("<ButtonRelease-1>", update_cursor_label)
text_box.bind("<MouseWheel>", lambda event: root.after_idle(update_line_numbers))
text_box.bind("<Configure>", update_line_numbers)

update_line_numbers()
update_cursor_label()
root.mainloop()
