import csv
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, scrolledtext


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

ods_content_frame = tk.Frame(ods_frame)
ods_content_frame.pack(fill="both", expand=True)

ods_action_frame = tk.Frame(ods_content_frame)
ods_action_frame.pack(side="right", fill="y", padx=(8, 0))

ods_result_box = scrolledtext.ScrolledText(
    ods_content_frame,
    height=12,
    font=("Consolas", 11),
    bg="white",
    fg="black",
)
ods_result_box.pack(side="left", fill="both", expand=True)

text_box.tag_config("error", foreground="red")
text_box.tag_config("bracket_error", background="red", foreground="white")
text_box.tag_config("line_error", foreground="red")

FUNCTION_LIKE_WORDS = [
    "ZEROIFNULL", "OREPLACE", "ISNULL", "POSITION", "CHAR_LENGTH",
    "CHARACTER_LENGTH", "SUM", "COUNT", "AVG", "MIN", "MAX", "NVL",
    "TRIM", "SUBSTR", "ROW_NUMBER",
]

TYPO_MAP = {
    "SELCET": "SELECT", "SLECT": "SELECT", "SELEECT": "SELECT", "SELECTE": "SELECT",
    "FORM": "FROM", "FOMR": "FROM", "FRON": "FROM",
    "WHRE": "WHERE", "HWERE": "WHERE", "WHEER": "WHERE",
    "INSRET": "INSERT", "INSER": "INSERT",
    "UDPATE": "UPDATE", "UPDAET": "UPDATE",
    "DELTE": "DELETE", "DLEET": "DELETE",
    "GRUOP": "GROUP",
    "ODRER": "ORDER", "OREDER": "ORDER",
    "HAIVNG": "HAVING", "HAVNG": "HAVING",
    "JOIIN": "JOIN", "JION": "JOIN",
    "VLAUES": "VALUES", "VALEUS": "VALUES",
    "CERATE": "CREATE", "CRAETE": "CREATE",
    "TABEL": "TABLE", "TALBE": "TABLE",
    "DISTINT": "DISTINCT", "DISTNCT": "DISTINCT",
    "BEWEEN": "BETWEEN", "BETWEN": "BETWEEN",
    "UINON": "UNION", "UNOIN": "UNION",
    "MERG": "MERGE", "MREGE": "MERGE",
    "DISTINCT": "DISTICT"
}

qualify_state = {
    "window": None,
    "input_box": None,
    "output_box": None,
}


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


def indent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else "" for line in text.splitlines())


def find_top_level_keyword(masked_sql: str, keyword: str, start: int = 0) -> int:
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    depth = 0

    for index, char in enumerate(masked_sql[start:], start=start):
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif depth == 0:
            match = pattern.match(masked_sql, index)
            if match:
                return match.start()
    return -1


def split_top_level_commas(text: str, masked_text: str):
    parts = []
    start = 0
    depth = 0

    for index, char in enumerate(masked_text):
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1

    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def find_matching_close_paren(masked_text: str, open_pos: int) -> int:
    """Return absolute index of the ')' matching the '(' at open_pos, or -1."""
    depth = 0
    for i in range(open_pos, len(masked_text)):
        if masked_text[i] == "(":
            depth += 1
        elif masked_text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def derive_outer_column_name(select_item: str) -> str:
    explicit_alias = re.search(r"\bAS\s+([A-Z][A-Z0-9_$#]*)\s*$", select_item, re.IGNORECASE)
    if explicit_alias:
        return explicit_alias.group(1)

    bare_alias = re.search(r"\s+([A-Z][A-Z0-9_$#]*)\s*$", select_item, re.IGNORECASE)
    if bare_alias and ")" not in bare_alias.group(1):
        leading = select_item[:bare_alias.start()].rstrip()
        if leading and not leading.endswith("."):
            return bare_alias.group(1)

    direct_column = re.search(r"(?:^|\.)([A-Z][A-Z0-9_$#]*)\s*$", select_item, re.IGNORECASE)
    if direct_column:
        return direct_column.group(1)

    return select_item.strip()


def build_outer_select_list(select_list_sql: str, select_list_masked: str) -> str:
    items = split_top_level_commas(select_list_sql, select_list_masked)
    if not items:
        return "*"

    distinct_prefix = ""
    first_item = items[0]
    distinct_match = re.match(r"^\s*DISTINCT\b", first_item, re.IGNORECASE)
    if distinct_match:
        distinct_prefix = "DISTINCT "
        items[0] = first_item[distinct_match.end():].strip()
        if not items[0]:
            items = items[1:]

    outer_items = [derive_outer_column_name(item) for item in items if item.strip()]
    if not outer_items:
        return distinct_prefix + "*"

    return distinct_prefix + ",\n       ".join(outer_items)


def extract_qualify_statement_parts(sql: str):
    masked_sql = mask_preserve_length(sql)
    qualify_pos = find_top_level_keyword(masked_sql, "QUALIFY")
    if qualify_pos == -1:
        raise ValueError("找不到頂層 QUALIFY")

    prefix = sql[:qualify_pos].rstrip()
    qualify_clause = sql[qualify_pos:].strip().rstrip(";").strip()
    masked_prefix = masked_sql[:qualify_pos]

    select_pos = find_top_level_keyword(masked_prefix, "SELECT")
    if select_pos == -1:
        raise ValueError("找不到可轉換的 SELECT 區段")

    statement_prefix = prefix[:select_pos].rstrip()
    select_sql = prefix[select_pos:].rstrip()
    select_masked = masked_prefix[select_pos:].rstrip()

    from_pos = find_top_level_keyword(select_masked, "FROM")
    if from_pos == -1:
        raise ValueError("SELECT 區段找不到 FROM")

    select_keyword = re.match(r"\s*SELECT\b", select_sql, re.IGNORECASE)
    select_list_sql = select_sql[select_keyword.end():from_pos].strip()
    select_list_masked = select_masked[select_keyword.end():from_pos].strip()
    from_sql = select_sql[from_pos:].strip()

    return {
        "statement_prefix": statement_prefix,
        "select_list_sql": select_list_sql,
        "select_list_masked": select_list_masked,
        "from_sql": from_sql,
        "qualify_clause": qualify_clause,
    }


def parse_qualify_clause(qualify_clause: str):

    qualify_clause = qualify_clause.strip()

    # CASE 1:
    # QUALIFY ROW_NUMBER() OVER (...) = 1

    pattern_window = re.compile(
        r"^QUALIFY\s+"
        r"(?P<func>ROW_NUMBER|RANK|DENSE_RANK)\s*\(\s*\)\s*"
        r"OVER\s*(?P<over>\(.*\))\s*"
        r"(?P<operator>=|<=|<|>=|>)\s*(?P<value>\d+)\s*$",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern_window.match(qualify_clause)

    if match:
        return {
            "mode": "window",
            "function_name": match.group("func").upper(),
            "over_clause": match.group("over").strip(),
            "operator": match.group("operator"),
            "value": match.group("value"),
        }

    # CASE 2:
    # QUALIFY RN = 1

    pattern_alias = re.compile(
        r"^QUALIFY\s+"
        r"(?P<alias>[A-Z][A-Z0-9_$#]*)\s*"
        r"(?P<operator>=|<=|<|>=|>)\s*"
        r"(?P<value>\d+)\s*$",
        re.IGNORECASE,
    )

    match = pattern_alias.match(qualify_clause)

    if match:
        return {
            "mode": "alias",
            "alias": match.group("alias"),
            "operator": match.group("operator"),
            "value": match.group("value"),
        }

    raise ValueError(
        "目前僅支援：\n"
        "1. QUALIFY ROW_NUMBER/RANK/DENSE_RANK OVER (...) = 數字\n"
        "2. QUALIFY alias = 數字"
    )


def convert_qualify_sql(sql: str) -> str:

    parts = extract_qualify_statement_parts(sql)
    qualify = parse_qualify_clause(parts["qualify_clause"])

    outer_select_list = build_outer_select_list(
        parts["select_list_sql"],
        parts["select_list_masked"]
    )

    # CASE 1:
    # QUALIFY ROW_NUMBER() OVER (...) = 1

    if qualify["mode"] == "window":

        analytic_line = (
            f"{qualify['function_name']}() "
            f"OVER {qualify['over_clause']} RN"
        )

        inner_select = (
            "SELECT " + parts["select_list_sql"] + ",\n"
            f"       {analytic_line}\n"
            + parts["from_sql"]
        ).strip()

        where_clause = (
            f"RN {qualify['operator']} {qualify['value']}"
        )

    # CASE 2:
    # QUALIFY RN = 1

    else:

        inner_select = (
            "SELECT " + parts["select_list_sql"] + "\n"
            + parts["from_sql"]
        ).strip()

        where_clause = (
            f"{qualify['alias']} "
            f"{qualify['operator']} "
            f"{qualify['value']}"
        )

    converted_parts = []

    if parts["statement_prefix"]:
        converted_parts.append(parts["statement_prefix"])

    converted_parts.append(f"SELECT {outer_select_list}")
    converted_parts.append("FROM")
    converted_parts.append("(")
    converted_parts.append(indent_block(inner_select, 4))
    converted_parts.append(")")
    converted_parts.append(f"WHERE {where_clause}")
    converted_parts.append(";")

    return "\n".join(converted_parts)


def clear_qualify_output():
    output_box = qualify_state["output_box"]
    if output_box is None:
        return
    output_box.delete("1.0", tk.END)


def run_qualify_conversion():
    input_box = qualify_state["input_box"]
    output_box = qualify_state["output_box"]
    if input_box is None or output_box is None:
        return

    sql = input_box.get("1.0", tk.END).strip()
    if not sql:
        messagebox.showwarning("QUALIFY 轉換", "請先輸入含 QUALIFY 的 SQL")
        return

    try:
        converted = convert_qualify_sql(sql)
    except ValueError as exc:
        converted = f"無法自動轉換：{exc}"

    output_box.delete("1.0", tk.END)
    output_box.insert("1.0", converted)


def open_qualify_converter():
    window = qualify_state["window"]
    if window is not None and window.winfo_exists():
        window.lift()
        window.focus_force()
        return

    window = tk.Toplevel(root)
    window.title("QUALIFY 轉換")
    window.geometry("1000x700")
    qualify_state["window"] = window

    def on_close():
        current_window = qualify_state["window"]
        if current_window is not None and current_window.winfo_exists():
            current_window.destroy()
        qualify_state["window"] = None
        qualify_state["input_box"] = None
        qualify_state["output_box"] = None

    window.protocol("WM_DELETE_WINDOW", on_close)

    input_frame = tk.LabelFrame(window, text="QUALIFY SQL 輸入")
    input_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

    input_box = scrolledtext.ScrolledText(
        input_frame,
        height=14,
        font=("Consolas", 11),
        bg="white",
        fg="black",
        wrap="none",
    )
    input_box.pack(fill="both", expand=True, padx=8, pady=8)
    qualify_state["input_box"] = input_box

    action_frame = tk.Frame(window)
    action_frame.pack(fill="x", padx=10, pady=5)

    tk.Button(
        action_frame,
        text="轉換",
        font=("Microsoft JhengHei", 11),
        command=run_qualify_conversion,
    ).pack(side="left")

    tk.Button(
        action_frame,
        text="清空結果",
        font=("Microsoft JhengHei", 11),
        command=clear_qualify_output,
    ).pack(side="left", padx=(8, 0))

    output_frame = tk.LabelFrame(window, text="Oracle 建議轉換")
    output_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    output_box = scrolledtext.ScrolledText(
        output_frame,
        height=14,
        font=("Consolas", 11),
        bg="white",
        fg="black",
        wrap="none",
    )
    output_box.pack(fill="both", expand=True, padx=8, pady=8)
    qualify_state["output_box"] = output_box


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


def check_alias_without_join(statements, issues):
    alias_column_pattern = re.compile(r"\b([A-Z][A-Z0-9_$#]*)\.([A-Z][A-Z0-9_$#]*)\b", re.IGNORECASE)
    schema_table_pattern = re.compile(
        r"^\s*(?:FROM|JOIN|UPDATE|INTO|DELETE\s+FROM|MERGE\s+INTO)\s+"
        r"[A-Z0-9_$#]+\.([A-Z0-9_$#]+)",
        re.IGNORECASE,
    )

    for statement in statements:
        if re.search(r"\bJOIN\b", statement.masked_text, re.IGNORECASE):
            continue

        for match in alias_column_pattern.finditer(statement.masked_text):
            line_start = statement.masked_text.rfind("\n", 0, match.start()) + 1
            line_end = statement.masked_text.find("\n", match.start())
            if line_end == -1:
                line_end = len(statement.masked_text)
            line_text = statement.masked_text[line_start:line_end]

            if schema_table_pattern.search(line_text):
                continue

            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues,
                line_no,
                "未使用 JOIN 時，不應使用別名.欄位 的引用方式",
                "syntax",
            )


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


def check_typos(masked_sql, issues):
    for typo, correct in TYPO_MAP.items():
        for match in re.finditer(rf"\b{re.escape(typo)}\b", masked_sql, re.IGNORECASE):
            line_no = masked_sql.count("\n", 0, match.start()) + 1
            line_start = masked_sql.rfind("\n", 0, match.start()) + 1
            start_col = match.start() - line_start
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues,
                line_no,
                f"疑似打字錯誤：'{match.group(0).upper()}' -> 是否為 '{correct}'？",
                "syntax",
            )


def check_insert_column_count(statements, issues):
    for statement in statements:
        if statement.first_keyword != "INSERT":
            continue

        masked = statement.masked_text
        sql = statement.text

        insert_match = re.search(
            r"\bINSERT\s+INTO\s+[A-Z0-9_.$#\"]+\s*\(",
            masked, re.IGNORECASE,
        )
        if not insert_match:
            continue

        col_open = insert_match.end() - 1
        col_close = find_matching_close_paren(masked, col_open)
        if col_close == -1:
            continue

        col_parts = [
            p for p in split_top_level_commas(
                sql[col_open + 1:col_close],
                masked[col_open + 1:col_close],
            )
            if p.strip()
        ]
        col_count = len(col_parts)
        if col_count == 0:
            continue

        after = col_close + 1

        sel_match = re.search(r"\bSELECT\b", masked[after:], re.IGNORECASE)
        val_match = re.search(r"\bVALUES\s*\(", masked[after:], re.IGNORECASE)

        if sel_match:
            sel_end_abs = after + sel_match.end()

            distinct_m = re.match(r"\s*DISTINCT\b", masked[sel_end_abs:], re.IGNORECASE)
            if distinct_m:
                sel_end_abs += distinct_m.end()

            from_pos = find_top_level_keyword(masked, "FROM", sel_end_abs)
            if from_pos == -1:
                continue

            sel_list_masked = masked[sel_end_abs:from_pos].strip()
            if re.fullmatch(r"\s*\*\s*", sel_list_masked):
                continue

            sel_parts = [
                p for p in split_top_level_commas(
                    sql[sel_end_abs:from_pos].strip(),
                    sel_list_masked,
                )
                if p.strip()
            ]
            sel_count = len(sel_parts)

            if col_count != sel_count:
                line_no = statement.start_line
                add_issue(
                    issues, line_no,
                    f"INSERT 欄位數({col_count})與 SELECT 欄位數({sel_count})不一致",
                    "syntax",
                )

        elif val_match:
            val_open_abs = after + val_match.end() - 1
            val_close_abs = find_matching_close_paren(masked, val_open_abs)
            if val_close_abs == -1:
                continue

            val_parts = [
                p for p in split_top_level_commas(
                    sql[val_open_abs + 1:val_close_abs],
                    masked[val_open_abs + 1:val_close_abs],
                )
                if p.strip()
            ]
            val_count = len(val_parts)

            if col_count != val_count:
                line_no = statement.start_line
                add_issue(
                    issues, line_no,
                    f"INSERT 欄位數({col_count})與 VALUES 數量({val_count})不一致",
                    "syntax",
                )


def check_oracle_structure(statements, issues):
    for statement in statements:
        masked = statement.masked_text

        # = NULL / != NULL / <> NULL
        for match in re.finditer(r"(=|!=|<>)\s*NULL\b", masked, re.IGNORECASE):
            op = match.group(1)
            suggestion = "IS NULL" if op == "=" else "IS NOT NULL"
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues, line_no,
                f"NULL 比較應使用 {suggestion}，不可寫 '{op} NULL'",
                "syntax",
            )

        # NULL = / NULL != / NULL <>
        for match in re.finditer(r"\bNULL\s*(=|!=|<>)", masked, re.IGNORECASE):
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(
                issues, line_no,
                "NULL 比較應使用 IS NULL / IS NOT NULL，不可直接用 = 或 <> NULL",
                "syntax",
            )

        # ROWNUM 在 WHERE 條件 + 同層 ORDER BY -> 排序失效風險
        where_pos = find_top_level_keyword(masked, "WHERE")
        order_pos = find_top_level_keyword(masked, "ORDER")
        if where_pos != -1 and order_pos != -1 and order_pos > where_pos:
            if re.search(r"\bROWNUM\b", masked[where_pos:order_pos], re.IGNORECASE):
                add_issue(
                    issues, statement.start_line,
                    "ROWNUM 與 ORDER BY 同層：ROWNUM 篩選在排序前執行，結果可能不符預期，建議改用子查詢",
                    "syntax",
                )

        # SELECT 無 FROM（Oracle 需要 FROM DUAL）
        if statement.first_keyword == "SELECT":
            if find_top_level_keyword(masked, "FROM") == -1:
                add_issue(
                    issues, statement.start_line,
                    "Oracle SELECT 若無查詢來源表，應加上 FROM DUAL",
                    "syntax",
                )


def check_insert_no_column_list(statements, issues):
    for statement in statements:
        if statement.first_keyword != "INSERT":
            continue
        masked = statement.masked_text
        # 負向預視必須包含 \s*，否則 \s* 回溯後看到空格就誤判通過
        match = re.search(
            r"\bINSERT\s+INTO\s+[A-Z0-9_.$#\"]+(?!\s*\()",
            masked, re.IGNORECASE,
        )
        if match:
            line_no = statement.start_line
            add_issue(
                issues, line_no,
                "INSERT 未指定欄位清單，若目標表結構異動將導致 ORA-00947，建議補上明確欄位清單",
                "syntax",
            )


def check_group_by_position(statements, issues):
    group_by_pattern = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)
    terminal_keywords = ("HAVING", "ORDER", "UNION", "INTERSECT", "MINUS", "EXCEPT")

    for statement in statements:
        masked = statement.masked_text
        sql = statement.text

        for match in group_by_pattern.finditer(masked):
            # 跳過子查詢內部的 GROUP BY（括號深度 > 0）
            depth = 0
            for ch in masked[:match.start()]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            if depth != 0:
                continue

            after = match.end()

            # 找出頂層 GROUP BY 子句的結尾
            clause_end = len(masked)
            for kw in terminal_keywords:
                pos = find_top_level_keyword(masked, kw, after)
                if -1 < pos < clause_end:
                    clause_end = pos

            items = split_top_level_commas(
                sql[after:clause_end],
                masked[after:clause_end],
            )

            if any(re.match(r"^\s*\d+\s*$", item) for item in items):
                line_no, start_col = statement_line_col(statement, match.start())
                add_tag(line_no, start_col, start_col + len(match.group(0)))
                add_issue(
                    issues, line_no,
                    "GROUP BY 使用位置編號，Oracle group_by_position_enabled 預設 FALSE，需改為明確欄位名稱",
                    "syntax",
                )


def check_blank_lines_in_statement(statements, issues):
    for statement in statements:
        lines = statement.text.split("\n")
        for rel_idx, line in enumerate(lines):
            if not line.strip():
                abs_line = statement.start_line + rel_idx
                add_issue(
                    issues, abs_line,
                    "SQL 陳述式內有空行，SQL*Plus 將空行視為終止符，"
                    "PARTITION / 多行結構會在此被截斷，請移除空行",
                    "syntax",
                )


def _count_select_cols(branch_sql: str, branch_masked: str):
    """SELECT 欄位數計算輔助（UNION 一致性檢查用）；無法判斷時回傳 None。"""
    with_pos = find_top_level_keyword(branch_masked, "WITH")
    select_pos = find_top_level_keyword(branch_masked, "SELECT")
    if select_pos == -1:
        return None
    if with_pos != -1 and with_pos < select_pos:
        return None  # WITH CTE 結構太複雜，略過
    select_end = select_pos + len("SELECT")
    dm = re.match(r"\s+DISTINCT\b", branch_masked[select_end:], re.IGNORECASE)
    if dm:
        select_end += dm.end()
    from_pos = find_top_level_keyword(branch_masked, "FROM", select_end)
    if from_pos == -1:
        return None
    col_masked = branch_masked[select_end:from_pos].strip()
    if re.fullmatch(r"\s*\*\s*", col_masked):
        return None  # SELECT * 無法計數
    parts = [p for p in split_top_level_commas(
        branch_sql[select_end:from_pos].strip(), col_masked) if p.strip()]
    return len(parts) if parts else None


# ── DML 安全性檢查 ───────────────────────────────────────────────────────────

def check_dml_without_where(statements, issues):
    for statement in statements:
        masked = statement.masked_text
        kw = statement.first_keyword

        if kw == "UPDATE":
            if find_top_level_keyword(masked, "WHERE") == -1:
                add_issue(issues, statement.start_line,
                    "UPDATE 缺少 WHERE 條件，將更新全表所有資料列，請確認是否刻意為之",
                    "syntax")

        elif kw == "DELETE":
            if find_top_level_keyword(masked, "WHERE") == -1:
                add_issue(issues, statement.start_line,
                    "DELETE 缺少 WHERE 條件，將刪除全表所有資料列，請確認是否刻意為之",
                    "syntax")


# ── 聚合 / GROUP BY 結構 ──────────────────────────────────────────────────────

def check_having_without_group_by(statements, issues):
    for statement in statements:
        masked = statement.masked_text
        having_pos = find_top_level_keyword(masked, "HAVING")
        if having_pos == -1:
            continue
        if find_top_level_keyword(masked, "GROUP") == -1:
            line_no, start_col = statement_line_col(statement, having_pos)
            add_tag(line_no, start_col, start_col + len("HAVING"))
            add_issue(issues, line_no,
                "HAVING 缺少對應的 GROUP BY，Oracle 將報語法錯誤 ORA-00935", "syntax")


def check_redundant_distinct(statements, issues):
    for statement in statements:
        masked = statement.masked_text
        select_pos = find_top_level_keyword(masked, "SELECT")
        if select_pos == -1:
            continue
        after_select = masked[select_pos + len("SELECT"):]
        if not re.match(r"\s+DISTINCT\b", after_select, re.IGNORECASE):
            continue
        if find_top_level_keyword(masked, "GROUP") != -1:
            line_no, start_col = statement_line_col(statement, select_pos)
            add_issue(issues, line_no,
                "SELECT DISTINCT 與 GROUP BY 同時使用，DISTINCT 冗餘，建議移除", "syntax")


# ── JOIN / 子查詢結構 ─────────────────────────────────────────────────────────

def check_cartesian_join(statements, issues):
    for statement in statements:
        masked = statement.masked_text
        if re.search(r"\bJOIN\b", masked, re.IGNORECASE):
            continue
        from_pos = find_top_level_keyword(masked, "FROM")
        if from_pos == -1:
            continue
        from_end = len(masked)
        for kw in ("WHERE", "GROUP", "ORDER", "HAVING", "UNION", "INTERSECT", "MINUS"):
            pos = find_top_level_keyword(masked, kw, from_pos + 4)
            if -1 < pos < from_end:
                from_end = pos
        depth = 0
        for ch in masked[from_pos + 4:from_end]:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                line_no, start_col = statement_line_col(statement, from_pos)
                add_issue(issues, line_no,
                    "FROM 使用逗號分隔多表（隱式 CROSS JOIN），可能產生笛卡爾積，"
                    "建議改用明確 JOIN ... ON 語法", "syntax")
                break


def check_not_in_subquery(statements, issues):
    pattern = re.compile(r"\bNOT\s+IN\s*\(\s*SELECT\b", re.IGNORECASE)
    for statement in statements:
        for match in pattern.finditer(statement.masked_text):
            line_no, start_col = statement_line_col(statement, match.start())
            end_col = start_col + len("NOT IN")
            add_tag(line_no, start_col, end_col)
            add_issue(issues, line_no,
                "NOT IN (SELECT...) 若子查詢結果含 NULL，整個條件回傳空集合，"
                "建議改用 NOT EXISTS 以避免 NULL 陷阱", "syntax")


# ── UNION 欄位數一致性 ────────────────────────────────────────────────────────

def check_union_column_count(statements, issues):
    union_pattern = re.compile(
        r"\bUNION(?:\s+ALL)?\b|\bINTERSECT\b|\bMINUS\b|\bEXCEPT\b", re.IGNORECASE)

    for statement in statements:
        masked = statement.masked_text
        sql = statement.text

        split_pairs = []
        for match in union_pattern.finditer(masked):
            depth = 0
            for ch in masked[:match.start()]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            if depth == 0:
                split_pairs.append((match.start(), match.end()))

        if not split_pairs:
            continue

        # 建立各分支範圍
        boundaries = []
        prev = 0
        for start, end in split_pairs:
            boundaries.append((prev, start))
            prev = end
        boundaries.append((prev, len(masked)))

        counts = [_count_select_cols(sql[s:e], masked[s:e]) for s, e in boundaries]
        valid = [c for c in counts if c is not None]
        if len(valid) >= 2 and len(set(valid)) > 1:
            counts_str = " / ".join(
                str(c) if c is not None else "?" for c in counts)
            add_issue(issues, statement.start_line,
                f"UNION / INTERSECT / MINUS 各分支欄位數不一致（{counts_str}），"
                "Oracle 將報 ORA-01789", "syntax")


# ── ORDER BY 結構 ─────────────────────────────────────────────────────────────

def check_order_by_position(statements, issues):
    ob_pattern = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)
    for statement in statements:
        masked = statement.masked_text
        sql = statement.text
        for match in ob_pattern.finditer(masked):
            depth = 0
            for ch in masked[:match.start()]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            if depth != 0:
                continue
            after = match.end()
            fetch_pos = find_top_level_keyword(masked, "FETCH", after)
            clause_end = fetch_pos if fetch_pos != -1 else len(masked)
            items = split_top_level_commas(sql[after:clause_end], masked[after:clause_end])
            has_pos = any(
                re.match(r"^\s*\d+\s*$",
                    re.sub(r"\b(?:ASC|DESC)\b", "", item, flags=re.IGNORECASE).strip())
                for item in items
            )
            if has_pos:
                line_no, start_col = statement_line_col(statement, match.start())
                add_tag(line_no, start_col, start_col + len(match.group(0)))
                add_issue(issues, line_no,
                    "ORDER BY 使用位置編號，可讀性差且維護困難，建議改為明確欄位名稱",
                    "syntax")


# ── 表達式 / 條件邏輯 ─────────────────────────────────────────────────────────

def check_like_no_wildcard(statements, issues):
    # 在原始 SQL（非 masked）中搜尋，才能看到字串內容
    pattern = re.compile(r"\bLIKE\s+'([^'%_\n]*)'", re.IGNORECASE)
    for statement in statements:
        for match in pattern.finditer(statement.text):
            if not match.group(1):          # LIKE '' 另由 empty_string 檢查
                continue
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(issues, line_no,
                f"LIKE '{match.group(1)}' 不含萬用字元(%/_)，效果等同 =，"
                "建議改用 = 或確認是否遺漏 %", "syntax")


_ORACLE_TYPES = (
    r"DATE|TIMESTAMP|NUMBER|DECIMAL|INTEGER|INT\b|SMALLINT|FLOAT|REAL|"
    r"BINARY_FLOAT|BINARY_DOUBLE|VARCHAR2|CHAR|NVARCHAR2|NCHAR|"
    r"CLOB|BLOB|NCLOB|RAW|INTERVAL"
)
_COL_DEF_START = re.compile(
    rf"^\s+[A-Z_][A-Z0-9_$#]*\s+(?:{_ORACLE_TYPES})\b",
    re.IGNORECASE,
)


def check_create_table_col_missing_comma(statements, issues):
    """偵測 CREATE TABLE 欄位定義清單中連續欄位之間缺少逗號的情況。"""
    for statement in statements:
        if statement.first_keyword != "CREATE":
            continue
        masked = statement.masked_text
        sql = statement.text
        if not re.search(r"\bTABLE\b", masked, re.IGNORECASE):
            continue

        # 找到緊接資料表名稱的 (，即欄位定義清單的開頭
        table_match = re.search(
            r"\bCREATE\s+(?:\w+\s+)*TABLE\s+[^\s(]+\s*\(",
            masked, re.IGNORECASE,
        )
        if not table_match:
            continue

        col_open  = table_match.end() - 1
        col_close = find_matching_close_paren(masked, col_open)
        if col_close == -1:
            continue

        col_block_sql    = sql[col_open + 1:col_close]
        col_block_masked = masked[col_open + 1:col_close]

        # 欄位區塊第一行的絕對行號偏移量
        base_offset = masked[:col_open + 1].count("\n")

        lines_sql    = col_block_sql.split("\n")
        lines_masked = col_block_masked.split("\n")

        prev_idx = -1  # 前一個有效行（非空白、非純註解）的索引

        for i, (lsql, lmasked) in enumerate(zip(lines_sql, lines_masked)):
            if not lmasked.strip():
                continue
            if lsql.strip().startswith(("--", "/*")):
                continue

            # 此行是否為新欄位定義的起始（識別符 + 型別關鍵字）
            if _COL_DEF_START.match(lmasked):
                if prev_idx >= 0:
                    prev_clean = re.sub(r"--.*$", "", lines_sql[prev_idx]).rstrip()
                    if not prev_clean.endswith(","):
                        abs_line = statement.start_line + base_offset + prev_idx
                        add_tag(abs_line, 0, 0, "line_error")
                        add_issue(
                            issues, abs_line,
                            "CREATE TABLE 欄位定義之間缺少逗號",
                            "syntax",
                        )

            prev_idx = i


def check_partition_missing_comma(statements, issues):
    """偵測 PARTITION BY 定義區塊中 VALUES LESS THAN (...) 後缺少逗號的情況。"""
    vlt_pattern = re.compile(r"\bVALUES\s+(?:LESS\s+THAN\s*)?\(", re.IGNORECASE)

    for statement in statements:
        if statement.first_keyword != "CREATE":
            continue
        masked = statement.masked_text
        if not re.search(r"\bPARTITION\s+BY\b", masked, re.IGNORECASE):
            continue

        for match in vlt_pattern.finditer(masked):
            paren_open = match.end() - 1
            paren_close = find_matching_close_paren(masked, paren_open)
            if paren_close == -1:
                continue

            # 找 ) 之後第一個非空白字元
            rest = masked[paren_close + 1:]
            next_nonws = re.search(r"\S", rest)
            if not next_nonws:
                continue

            # 若緊接的是 PARTITION 關鍵字（不是逗號），則缺少逗號
            if re.match(r"PARTITION\b", rest[next_nonws.start():], re.IGNORECASE):
                line_no, start_col = statement_line_col(statement, paren_close)
                add_tag(line_no, start_col, start_col + 1)
                add_issue(
                    issues, line_no,
                    "PARTITION 定義之間缺少逗號，VALUES LESS THAN (...) 後應補上 ,",
                    "syntax",
                )


def check_empty_string_comparison(statements, issues):
    # Oracle 中 '' 等同 NULL，= '' 條件永遠不成立
    pattern = re.compile(r"(?:(?:=|<>|!=)\s*''|''\s*(?:=|<>|!=))")
    for statement in statements:
        for match in pattern.finditer(statement.text):
            line_no, start_col = statement_line_col(statement, match.start())
            add_tag(line_no, start_col, start_col + len(match.group(0)))
            add_issue(issues, line_no,
                "Oracle 空字串 '' 等同於 NULL，= '' 條件永遠不成立，應改用 IS NULL",
                "syntax")


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
    check_alias_without_join(statements, issues)
    check_primary_index_context(statements, issues)
    check_index_function(statements, issues)
    check_function_parentheses(masked_sql, issues)
    check_generic_qualify(statements, issues)
    check_qualify_conversion(statements, issues)
    check_format_conversion(statements, issues)
    check_inline_view_alias(statements, issues)
    check_typos(masked_sql, issues)
    check_insert_column_count(statements, issues)
    check_oracle_structure(statements, issues)
    check_insert_no_column_list(statements, issues)
    check_group_by_position(statements, issues)
    check_blank_lines_in_statement(statements, issues)
    check_dml_without_where(statements, issues)
    check_having_without_group_by(statements, issues)
    check_redundant_distinct(statements, issues)
    check_cartesian_join(statements, issues)
    check_not_in_subquery(statements, issues)
    check_union_column_count(statements, issues)
    check_order_by_position(statements, issues)
    check_like_no_wildcard(statements, issues)
    check_empty_string_comparison(statements, issues)
    check_create_table_col_missing_comma(statements, issues)
    check_partition_missing_comma(statements, issues)
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

qualify_btn = tk.Button(
    ods_action_frame,
    text="QUALIFY\n轉換",
    font=("Microsoft JhengHei", 11),
    width=10,
    command=open_qualify_converter,
)
qualify_btn.pack(anchor="n")


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
