import os
import sqlite3
import uuid
from datetime import datetime, timezone

# DATA_DIR defaults to sitting next to this file (repo root) - fine for local
# dev, where the working copy itself is the persistent store. On Render (or
# any host with an ephemeral filesystem), set DATA_DIR to a mounted
# persistent disk's path (e.g. /var/data) so nexus.db survives redeploys
# instead of being recreated empty by init_db() every time.
DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "nexus.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            key TEXT,
            description TEXT,
            jira_project_key TEXT,
            confluence_space_key TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            agent_name TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            content TEXT,
            is_external INTEGER NOT NULL DEFAULT 0,
            is_test_script INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES work_items(id) ON DELETE CASCADE,
            issuetype TEXT NOT NULL,
            summary TEXT NOT NULL,
            description TEXT,
            priority TEXT,
            jira_key TEXT,
            synced_at TEXT,
            code TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            work_item_id INTEGER REFERENCES work_items(id) ON DELETE CASCADE,
            code TEXT,
            title TEXT NOT NULL,
            steps TEXT,
            expected_result TEXT,
            priority TEXT,
            status TEXT NOT NULL DEFAULT 'Not Run',
            jira_key TEXT,
            synced_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS change_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            code TEXT,
            title TEXT NOT NULL,
            type TEXT,
            stage TEXT,
            priority TEXT,
            status TEXT NOT NULL DEFAULT 'Proposed',
            description TEXT,
            impact_summary TEXT,
            work_item_id INTEGER REFERENCES work_items(id) ON DELETE SET NULL,
            raised_by TEXT,
            raised_at TEXT NOT NULL,
            approved_by TEXT,
            decision_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS confluence_synced (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()

    # Migration for databases created before per-project Jira/Confluence targeting existed
    for column, coltype in (("jira_project_key", "TEXT"), ("confluence_space_key", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {column} {coltype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    # Migration for databases created before human-readable work item codes (EP001 etc.) existed
    try:
        conn.execute("ALTER TABLE work_items ADD COLUMN code TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Migration for databases created before test cases could be pushed to Jira
    for column, coltype in (("jira_key", "TEXT"), ("synced_at", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE test_cases ADD COLUMN {column} {coltype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.close()


# ============================================================
# PROJECTS
# ============================================================

def create_project(name, key, description, jira_project_key=None, confluence_space_key=None):
    project_id = uuid.uuid4().hex
    now = _now()
    conn = get_conn()
    conn.execute(
        "INSERT INTO projects (id, name, key, description, jira_project_key, confluence_space_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, name, key, description, jira_project_key or None, confluence_space_key or None, now, now),
    )
    conn.commit()
    conn.close()
    return {
        "id": project_id, "name": name, "key": key, "description": description,
        "jira_project_key": jira_project_key or None, "confluence_space_key": confluence_space_key or None,
        "created_at": now, "updated_at": now,
    }


def list_projects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_project_basic(project_id):
    """Lightweight lookup (no child rows) - used to resolve a project's own
    Jira/Confluence keys without paying for the full nested hydrate."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def touch_project(project_id):
    conn = get_conn()
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))
    conn.commit()
    conn.close()


def get_project(project_id):
    conn = get_conn()
    project_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project_row:
        conn.close()
        return None

    project = dict(project_row)
    project["chat_messages"] = [dict(r) for r in conn.execute(
        "SELECT * FROM chat_messages WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    project["agent_contributions"] = [dict(r) for r in conn.execute(
        "SELECT * FROM agent_contributions WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    project["knowledge_items"] = [dict(r) for r in conn.execute(
        "SELECT * FROM knowledge_items WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    project["artifacts"] = [dict(r) for r in conn.execute(
        "SELECT * FROM artifacts WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    work_item_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM work_items WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    project["work_items"] = _build_work_item_tree(work_item_rows)
    project["confluence_synced"] = [dict(r) for r in conn.execute(
        "SELECT * FROM confluence_synced WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]

    conn.close()
    return project


def delete_project(project_id):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


# ============================================================
# CHAT / AGENT CONTRIBUTIONS / KNOWLEDGE
# ============================================================

def add_chat_message(project_id, role, text):
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_messages (project_id, role, text, created_at) VALUES (?, ?, ?, ?)",
        (project_id, role, text, _now()),
    )
    conn.commit()
    conn.close()
    touch_project(project_id)


def add_agent_contribution(project_id, agent_name, text):
    conn = get_conn()
    conn.execute(
        "INSERT INTO agent_contributions (project_id, agent_name, text, created_at) VALUES (?, ?, ?, ?)",
        (project_id, agent_name, text, _now()),
    )
    conn.commit()
    conn.close()
    touch_project(project_id)


def add_knowledge_item(project_id, title, content, item_type):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO knowledge_items (project_id, title, content, type, created_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, title, content, item_type, _now()),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    touch_project(project_id)
    return new_id


def delete_knowledge_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM knowledge_items WHERE id = ?", (item_id,)).fetchone()
    conn.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    if row:
        touch_project(row["project_id"])


# ============================================================
# ARTIFACTS
# ============================================================

def replace_artifacts(project_id, files_list, test_script_names=None):
    """Full-replace semantics, matching the frontend's `window.vaultFiles = data.files`."""
    test_script_names = set(test_script_names or [])
    now = _now()
    conn = get_conn()
    conn.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
    for f in files_list:
        conn.execute(
            "INSERT INTO artifacts (project_id, name, url, content, is_external, is_test_script, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                f.get("name"),
                f.get("url"),
                f.get("content"),
                1 if f.get("external") else 0,
                1 if f.get("name") in test_script_names else 0,
                now,
            ),
        )
    conn.commit()
    conn.close()
    touch_project(project_id)


def add_artifacts(project_id, files_list):
    """Additive insert (used by /artifacts/recover's legacy-fallback path)."""
    now = _now()
    conn = get_conn()
    for f in files_list:
        conn.execute(
            "INSERT INTO artifacts (project_id, name, url, content, is_external, is_test_script, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, f.get("name"), f.get("url"), f.get("content"), 0, 0, now),
        )
    conn.commit()
    conn.close()
    touch_project(project_id)


def delete_artifact_by_name(project_id, name):
    conn = get_conn()
    conn.execute("DELETE FROM artifacts WHERE project_id = ? AND name = ?", (project_id, name))
    conn.commit()
    conn.close()
    touch_project(project_id)


# ============================================================
# WORK ITEMS (Epic / Story / Task / Subtask hierarchy) / JIRA
# ============================================================

def _build_work_item_tree(rows):
    """Assembles a flat list of work_item rows (each a dict with 'id' and
    'parent_id') into a nested tree: top-level items (parent_id IS NULL)
    each carrying a 'children' list, recursively."""
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r["parent_id"], []).append(dict(r))

    def attach_children(node):
        node["children"] = [attach_children(c) for c in by_parent.get(node["id"], [])]
        return node

    return [attach_children(r) for r in by_parent.get(None, [])]


CODE_PREFIXES = {"Epic": "EP", "Story": "STY", "Task": "TSK", "Subtask": "SUB"}


def _seed_code_counters(conn, project_id):
    """Highest existing numeric suffix per issuetype prefix for this project,
    so newly-generated drafts continue the sequence rather than restart it -
    codes on already-synced items are permanent and must never be reused."""
    counters = {}
    for issuetype, prefix in CODE_PREFIXES.items():
        rows = conn.execute(
            "SELECT code FROM work_items WHERE project_id = ? AND issuetype = ? AND code IS NOT NULL",
            (project_id, issuetype),
        ).fetchall()
        max_n = 0
        for r in rows:
            code = r["code"] or ""
            if code.startswith(prefix):
                try:
                    max_n = max(max_n, int(code[len(prefix):]))
                except ValueError:
                    pass
        counters[issuetype] = max_n
    return counters


def replace_unsynced_work_items(project_id, tree):
    """
    Deletes only never-synced items (jira_key IS NULL - cascades to their
    children via the FK) before inserting the fresh generated tree, so
    already-synced items keep their jira_key, code, and position permanently.
    Each inserted node gets a human-readable code (EP001, STY001, TSK001,
    SUB001, sequential per project+issuetype).
    `tree` is a list of nested dicts: {issuetype, summary, description,
    priority, children: [...]}.
    """
    now = _now()
    conn = get_conn()
    conn.execute("DELETE FROM work_items WHERE project_id = ? AND jira_key IS NULL", (project_id,))
    counters = _seed_code_counters(conn, project_id)

    def next_code(issuetype):
        prefix = CODE_PREFIXES.get(issuetype, "ITM")
        counters[issuetype] = counters.get(issuetype, 0) + 1
        return f"{prefix}{counters[issuetype]:03d}"

    def insert_node(node, parent_id):
        code = next_code(node.get("issuetype"))
        cur = conn.execute(
            "INSERT INTO work_items (project_id, parent_id, issuetype, summary, description, priority, jira_key, synced_at, code, created_at) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (project_id, parent_id, node.get("issuetype"), node.get("summary"), node.get("description"), node.get("priority"), code, now),
        )
        new_id = cur.lastrowid
        for child in node.get("children") or []:
            insert_node(child, new_id)

    for root_node in tree:
        insert_node(root_node, None)

    conn.commit()
    conn.close()
    touch_project(project_id)


def add_work_items(project_id, insertions):
    """
    Additive insert for the Draft pane's quick-add features (AI quick-create
    and the manual "+ Create" form) - unlike replace_unsynced_work_items,
    this never deletes existing drafts, it only appends. `insertions` is a
    list of {parent_code, node}: parent_code is an existing work_items.code
    in this project (or falsy to create a new top-level item), and node is
    a nested dict like the generation tree: {issuetype, summary,
    description, priority, children: [...]}. A node created earlier in the
    same call can be referenced as a later insertion's parent via its own
    freshly-assigned code, so "add a story and 3 tasks under it" works in
    one request. Returns the newly created rows (with their assigned codes).
    """
    now = _now()
    conn = get_conn()
    code_to_id = {
        r["code"]: r["id"] for r in conn.execute(
            "SELECT id, code FROM work_items WHERE project_id = ? AND code IS NOT NULL", (project_id,)
        ).fetchall()
    }
    counters = _seed_code_counters(conn, project_id)
    created = []

    def next_code(issuetype):
        prefix = CODE_PREFIXES.get(issuetype, "ITM")
        counters[issuetype] = counters.get(issuetype, 0) + 1
        return f"{prefix}{counters[issuetype]:03d}"

    def insert_node(node, parent_id):
        code = next_code(node.get("issuetype"))
        cur = conn.execute(
            "INSERT INTO work_items (project_id, parent_id, issuetype, summary, description, priority, jira_key, synced_at, code, created_at) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (project_id, parent_id, node.get("issuetype"), node.get("summary"), node.get("description"), node.get("priority"), code, now),
        )
        new_id = cur.lastrowid
        code_to_id[code] = new_id
        created.append({"id": new_id, "code": code, "issuetype": node.get("issuetype"), "summary": node.get("summary"), "parent_id": parent_id})
        for child in node.get("children") or []:
            insert_node(child, new_id)

    for ins in insertions:
        parent_code = ins.get("parent_code")
        parent_id = code_to_id.get(parent_code) if parent_code else None
        insert_node(ins["node"], parent_id)

    conn.commit()
    conn.close()
    touch_project(project_id)
    return created


def get_work_item_by_code(project_id, code):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM work_items WHERE project_id = ? AND code = ?", (project_id, code)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_work_item_tree(project_id):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM work_items WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    conn.close()
    return _build_work_item_tree(rows)


def get_work_items_by_ids(item_ids):
    if not item_ids:
        return []
    conn = get_conn()
    placeholders = ",".join("?" for _ in item_ids)
    rows = conn.execute(f"SELECT * FROM work_items WHERE id IN ({placeholders})", tuple(item_ids)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_work_items(project_id):
    """Flat (non-tree) list of every work item for a project - used by the
    push-to-Jira flow to resolve parent chains regardless of what the user
    actually selected."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM work_items WHERE project_id = ?", (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_work_items_synced(project_id, results):
    """results: list of {id, jira_key} using the local work_items.id."""
    now = _now()
    conn = get_conn()
    for r in results:
        conn.execute(
            "UPDATE work_items SET jira_key = ?, synced_at = ? WHERE id = ? AND project_id = ?",
            (r.get("jira_key"), now, r.get("id"), project_id),
        )
    conn.commit()
    conn.close()
    touch_project(project_id)


def get_work_item_subtree(item_id):
    """The item plus all of its descendants (recursively), flat - used to
    figure out which Jira issues need deleting when a node with children
    is removed."""
    conn = get_conn()
    rows = conn.execute(
        """
        WITH RECURSIVE subtree(id) AS (
            SELECT id FROM work_items WHERE id = ?
            UNION ALL
            SELECT w.id FROM work_items w JOIN subtree s ON w.parent_id = s.id
        )
        SELECT * FROM work_items WHERE id IN (SELECT id FROM subtree)
        """,
        (item_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_work_item(item_id):
    """Deletes a work item and (via the FK's ON DELETE CASCADE) all of its
    descendants in one shot."""
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM work_items WHERE id = ?", (item_id,)).fetchone()
    conn.execute("DELETE FROM work_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    if row:
        touch_project(row["project_id"])


def get_test_cases(project_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM test_cases WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _seed_test_case_counter(conn, project_id):
    """Highest existing TC### suffix for this project, so newly-inserted test
    cases continue the sequence rather than restart it - codes on already
    Jira-synced test cases are permanent and must never be reused."""
    n = 0
    rows = conn.execute(
        "SELECT code FROM test_cases WHERE project_id = ? AND code IS NOT NULL", (project_id,)
    ).fetchall()
    for r in rows:
        code = r["code"] or ""
        if code.startswith("TC"):
            try:
                n = max(n, int(code[2:]))
            except ValueError:
                pass
    return n


def replace_test_cases(project_id, test_cases):
    """
    Deletes only never-synced test cases (jira_key IS NULL) before inserting
    the fresh generated batch, mirroring replace_unsynced_work_items - test
    cases already pushed to Jira keep their jira_key, code, and status
    permanently instead of being wiped on the next regeneration. `test_cases`
    is a list of dicts: {linked_code, title, steps, expected_result, priority}
    where linked_code is a work_items.code (e.g. "STY001") this test case covers.
    """
    now = _now()
    conn = get_conn()
    conn.execute("DELETE FROM test_cases WHERE project_id = ? AND jira_key IS NULL", (project_id,))

    code_to_id = {
        r["code"]: r["id"] for r in conn.execute(
            "SELECT id, code FROM work_items WHERE project_id = ? AND code IS NOT NULL", (project_id,)
        ).fetchall()
    }

    n = _seed_test_case_counter(conn, project_id)
    for tc in test_cases:
        n += 1
        conn.execute(
            "INSERT INTO test_cases (project_id, work_item_id, code, title, steps, expected_result, priority, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Not Run', ?)",
            (
                project_id,
                code_to_id.get(tc.get("linked_code")),
                f"TC{n:03d}",
                tc.get("title", "Untitled Test Case"),
                tc.get("steps"),
                tc.get("expected_result"),
                tc.get("priority"),
                now,
            ),
        )
    conn.commit()
    conn.close()
    touch_project(project_id)


def add_test_cases(project_id, work_item_id, test_cases):
    """
    Additive insert of test cases linked to ONE existing work item - used by
    the Jira Sync panel's per-item "Generate Test Cases" action, which never
    touches any other item's test cases. `test_cases` is a list of dicts:
    {title, steps, expected_result, priority}. Returns the newly created rows.
    """
    now = _now()
    conn = get_conn()
    n = _seed_test_case_counter(conn, project_id)
    created = []
    for tc in test_cases:
        n += 1
        code = f"TC{n:03d}"
        cur = conn.execute(
            "INSERT INTO test_cases (project_id, work_item_id, code, title, steps, expected_result, priority, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'Not Run', ?)",
            (
                project_id,
                work_item_id,
                code,
                tc.get("title", "Untitled Test Case"),
                tc.get("steps"),
                tc.get("expected_result"),
                tc.get("priority"),
                now,
            ),
        )
        created.append({"id": cur.lastrowid, "code": code, "title": tc.get("title", "Untitled Test Case")})
    conn.commit()
    conn.close()
    touch_project(project_id)
    return created


def get_test_cases_by_ids(test_case_ids):
    if not test_case_ids:
        return []
    conn = get_conn()
    placeholders = ",".join("?" for _ in test_case_ids)
    rows = conn.execute(f"SELECT * FROM test_cases WHERE id IN ({placeholders})", tuple(test_case_ids)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_test_cases_synced(project_id, results):
    """results: list of {id, jira_key} using the local test_cases.id."""
    now = _now()
    conn = get_conn()
    for r in results:
        conn.execute(
            "UPDATE test_cases SET jira_key = ?, synced_at = ? WHERE id = ? AND project_id = ?",
            (r.get("jira_key"), now, r.get("id"), project_id),
        )
    conn.commit()
    conn.close()
    touch_project(project_id)


def get_rtm_rows(project_id):
    """
    Assembles the Requirements Traceability Matrix: one row per Story/Task,
    joined up to its parent Epic and out to every Test Case that validates
    it (one row per test case; items with no test case yet get a single
    "not covered" row). Live Jira status is NOT included here - the caller
    fetches that separately and merges it in by jira_key, since it changes
    outside this app and shouldn't be cached in SQLite.
    """
    conn = get_conn()
    items = {r["id"]: dict(r) for r in conn.execute(
        "SELECT * FROM work_items WHERE project_id = ?", (project_id,)
    ).fetchall()}
    test_cases = [dict(r) for r in conn.execute(
        "SELECT * FROM test_cases WHERE project_id = ? ORDER BY id ASC", (project_id,)
    ).fetchall()]
    conn.close()

    tc_by_work_item = {}
    for tc in test_cases:
        tc_by_work_item.setdefault(tc["work_item_id"], []).append(tc)

    rows = []
    for item in items.values():
        if item["issuetype"] not in ("Story", "Task"):
            continue
        epic = items.get(item["parent_id"]) if item["parent_id"] else None
        linked_tests = tc_by_work_item.get(item["id"], [])
        base = {
            "epic_code": epic["code"] if epic else None,
            "epic_summary": epic["summary"] if epic else None,
            "item_id": item["id"],
            "item_code": item["code"],
            "item_type": item["issuetype"],
            "item_summary": item["summary"],
            "priority": item["priority"],
            "jira_key": item["jira_key"],
        }
        if linked_tests:
            for tc in linked_tests:
                rows.append({
                    **base,
                    "test_case_id": tc["id"],
                    "test_case_code": tc["code"],
                    "test_case_title": tc["title"],
                    "test_case_status": tc["status"],
                    "test_case_jira_key": tc.get("jira_key"),
                    "covered": True,
                })
        else:
            rows.append({
                **base,
                "test_case_id": None, "test_case_code": None, "test_case_title": None,
                "test_case_status": None, "test_case_jira_key": None, "covered": False,
            })

    rows.sort(key=lambda r: (r["epic_code"] or "￿", r["item_code"] or ""))
    return rows


def clear_work_item_sync_by_jira_key(jira_key):
    """When a Jira issue is deleted directly (not via the local tree), any
    local draft that pointed at it reverts to unsynced rather than being
    left with a dangling key."""
    conn = get_conn()
    conn.execute("UPDATE work_items SET jira_key = NULL, synced_at = NULL WHERE jira_key = ?", (jira_key,))
    conn.commit()
    conn.close()


# ============================================================
# CHANGE REQUESTS (Change Log / Scope Register)
# ============================================================

def _seed_cr_counter(conn, project_id):
    """Highest existing CR### suffix for this project, so new change requests
    continue the sequence rather than restart it."""
    n = 0
    rows = conn.execute(
        "SELECT code FROM change_requests WHERE project_id = ? AND code IS NOT NULL", (project_id,)
    ).fetchall()
    for r in rows:
        code = r["code"] or ""
        if code.startswith("CR"):
            try:
                n = max(n, int(code[2:]))
            except ValueError:
                pass
    return n


def create_change_request(project_id, fields):
    """
    fields: {title, type, stage, priority, description, impact_summary,
    work_item_code (optional - an existing work_items.code to link),
    raised_by, status (optional, defaults to 'Proposed')}.
    """
    now = _now()
    conn = get_conn()

    work_item_id = None
    work_item_code = fields.get("work_item_code")
    if work_item_code:
        row = conn.execute(
            "SELECT id FROM work_items WHERE project_id = ? AND code = ?", (project_id, work_item_code)
        ).fetchone()
        work_item_id = row["id"] if row else None

    n = _seed_cr_counter(conn, project_id) + 1
    code = f"CR{n:03d}"
    status = fields.get("status") or "Proposed"
    cur = conn.execute(
        """INSERT INTO change_requests
           (project_id, code, title, type, stage, priority, status, description, impact_summary,
            work_item_id, raised_by, raised_at, approved_by, decision_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id, code, fields.get("title", "Untitled Change"), fields.get("type"), fields.get("stage"),
            fields.get("priority"), status, fields.get("description"), fields.get("impact_summary"),
            work_item_id, fields.get("raised_by"), fields.get("raised_at") or now,
            fields.get("approved_by"), fields.get("decision_at"), now,
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    touch_project(project_id)
    return get_change_request(new_id)


def get_change_request(cr_id):
    conn = get_conn()
    row = conn.execute(
        """SELECT cr.*, wi.code AS work_item_code, wi.summary AS work_item_summary
           FROM change_requests cr LEFT JOIN work_items wi ON wi.id = cr.work_item_id
           WHERE cr.id = ?""",
        (cr_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_change_requests(project_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT cr.*, wi.code AS work_item_code, wi.summary AS work_item_summary
           FROM change_requests cr LEFT JOIN work_items wi ON wi.id = cr.work_item_id
           WHERE cr.project_id = ? ORDER BY cr.id ASC""",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_change_request(cr_id, fields):
    """Partial update - only columns present in `fields` are touched.
    `work_item_code` (an existing work_items.code, or '' to unlink) resolves
    to work_item_id same as create_change_request."""
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM change_requests WHERE id = ?", (cr_id,)).fetchone()
    if not row:
        conn.close()
        return None
    project_id = row["project_id"]

    updates = {}
    for col in ("title", "type", "stage", "priority", "status", "description", "impact_summary", "raised_by", "approved_by", "decision_at"):
        if col in fields:
            updates[col] = fields[col]
    if "work_item_code" in fields:
        code = fields.get("work_item_code")
        if code:
            wi = conn.execute("SELECT id FROM work_items WHERE project_id = ? AND code = ?", (project_id, code)).fetchone()
            updates["work_item_id"] = wi["id"] if wi else None
        else:
            updates["work_item_id"] = None

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE change_requests SET {set_clause} WHERE id = ?", (*updates.values(), cr_id))
        conn.commit()
    conn.close()
    touch_project(project_id)
    return get_change_request(cr_id)


def delete_change_request(cr_id):
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM change_requests WHERE id = ?", (cr_id,)).fetchone()
    conn.execute("DELETE FROM change_requests WHERE id = ?", (cr_id,))
    conn.commit()
    conn.close()
    if row:
        touch_project(row["project_id"])


# ============================================================
# CONFLUENCE
# ============================================================

def add_confluence_synced(project_id, name, url):
    conn = get_conn()
    conn.execute(
        "INSERT INTO confluence_synced (project_id, name, url, created_at) VALUES (?, ?, ?, ?)",
        (project_id, name, url, _now()),
    )
    conn.commit()
    conn.close()
    touch_project(project_id)
