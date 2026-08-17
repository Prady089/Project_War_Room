import os, re, time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import google.generativeai as genai
import json
import asyncio
import requests
from requests.auth import HTTPBasicAuth
from docx import Document
from docx.shared import Pt, Inches
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ============================================================
# CONFIGURATION
# ============================================================

WORKSPACE_DIR = os.path.join(os.getcwd(), "workspace")
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

# Mount Workspace for Live Preview
app.mount("/workspace", StaticFiles(directory=WORKSPACE_DIR), name="workspace")

# Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))

# ============================================================
# JIRA CONFIGURATION
# ============================================================

JIRA_URL          = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_USERNAME     = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN    = os.getenv("JIRA_API_TOKEN", "")
JIRA_PERSONAL_TOKEN = os.getenv("JIRA_PERSONAL_TOKEN", "")
JIRA_PROJECT_KEY  = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_SSL_VERIFY   = os.getenv("JIRA_SSL_VERIFY", "true").lower() != "false"

def jira_headers():
    if JIRA_PERSONAL_TOKEN:
        return {
            "Authorization": f"Bearer {JIRA_PERSONAL_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, None
    else:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN)

def jira_configured():
    if not JIRA_URL or not JIRA_PROJECT_KEY:
        return False
    if JIRA_PERSONAL_TOKEN:
        return True
    return bool(JIRA_USERNAME and JIRA_API_TOKEN)


# ============================================================
# LLM & DOCX UTILITY
# ============================================================

def llm(system, user):
    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system + "\n\nImportant: Do not recite copyrighted material or training data verbatim. Be creative and synthesize new logic based on requirements."
        )
        response = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        if hasattr(response, 'candidates') and response.candidates:
            if response.candidates[0].finish_reason == 4:
                return "AGENT ERROR: Recitation block (Finish Reason 4). Try re-phrasing your request slightly."
        return response.text.strip()
    except Exception as e:
        return f"LLM_ERROR: {str(e)}"

def save_as_docx(title, content, file_path):
    """
    Parses Markdown-like headers and paragraphs to output a clean DOCX file.
    """
    doc = Document()
    
    # Configure styles
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(11)
    
    doc.add_heading(title, level=0)
    
    lines = content.split('\n')
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        
        # Headers
        if line_strip.startswith('###'):
            h = doc.add_heading(line_strip.replace('###', '').strip(), level=3)
            h.paragraph_format.space_before = Pt(8)
            h.paragraph_format.space_after = Pt(4)
        elif line_strip.startswith('##'):
            h = doc.add_heading(line_strip.replace('##', '').strip(), level=2)
            h.paragraph_format.space_before = Pt(12)
            h.paragraph_format.space_after = Pt(6)
        elif line_strip.startswith('#'):
            h = doc.add_heading(line_strip.replace('#', '').strip(), level=1)
            h.paragraph_format.space_before = Pt(16)
            h.paragraph_format.space_after = Pt(8)
        # Bullet Lists
        elif line_strip.startswith('*') or line_strip.startswith('-'):
            clean_li = re.sub(r'^[\*\-]\s*', '', line_strip)
            doc.add_paragraph(clean_li, style='List Bullet')
        # Standard Paragraphs
        else:
            doc.add_paragraph(line_strip)
            
    doc.save(file_path)


def create_miro_flowchart(miro_token, board_name, steps):
    """
    Creates a new Miro board and maps the flowchart steps as visual connected rectangles.
    """
    if not miro_token or "test_token" in miro_token or len(miro_token) < 20:
        return "https://miro.com/app/board/uXjVPkMck5Q=/"
        
    try:
        headers = {
            "Authorization": f"Bearer {miro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 1. Create Board
        board_payload = {
            "name": board_name,
            "description": "Interactive Process Flowchart generated by Nexus.AI"
        }
        r = requests.post("https://api.miro.com/v2/boards", headers=headers, json=board_payload, timeout=10)
        if r.status_code not in (200, 201):
            return "https://miro.com/app/board/uXjVPkMck5Q=/"
            
        board_data = r.json()
        board_id = board_data.get("id")
        board_url = board_data.get("viewLink")
        
        # 2. Create Shapes for each step and link them
        created_shape_ids = []
        x_coord = 0
        
        for idx, step in enumerate(steps):
            title = step.get("title", f"Step {idx+1}")
            desc = step.get("text", "")
            
            # Create Shape
            shape_payload = {
                "data": {
                    "content": f"<h3>{title}</h3><p>{desc}</p>",
                    "shape": "rectangle"
                },
                "style": {
                    "fillColor": "#151f32",
                    "borderColor": "#10b981",
                    "color": "#e2e8f0"
                },
                "position": {
                    "x": x_coord,
                    "y": 0
                },
                "geometry": {
                    "width": 240,
                    "height": 130
                }
            }
            
            r_shape = requests.post(f"https://api.miro.com/v2/boards/{board_id}/shapes", headers=headers, json=shape_payload, timeout=5)
            if r_shape.status_code in (200, 201):
                shape_id = r_shape.json().get("id")
                created_shape_ids.append(shape_id)
                
                # Connect to previous shape
                if len(created_shape_ids) > 1:
                    prev_id = created_shape_ids[-2]
                    conn_payload = {
                        "startItem": {
                            "id": prev_id
                        },
                        "endItem": {
                            "id": shape_id
                        },
                        "style": {
                            "strokeColor": "#10b981",
                            "strokeWidth": "2.0"
                        }
                    }
                    requests.post(f"https://api.miro.com/v2/boards/{board_id}/connectors", headers=headers, json=conn_payload, timeout=5)
            
            x_coord += 350 # Spacing horizontally
            
        return board_url
    except Exception:
        return "https://miro.com/app/board/uXjVPkMck5Q=/"


# ============================================================
# INTERACTIVE BA CHAT INTERVIEW ENDPOINT
# ============================================================

@app.post("/chat/ba")
async def chat_ba(request: Request):
    body = await request.json()
    user_message = body.get("message", "")
    history = body.get("history", [])
    knowledge_list = body.get("knowledge", [])

    kb_context = ""
    if knowledge_list:
        kb_context = "\nACTIVE KNOWLEDGE BASE REFERENCES:\n"
        for k in knowledge_list:
            kb_context += f"- Title: {k.get('title')}\n  Context: {k.get('content')}\n"

    history_str = ""
    user_turns_count = 0
    for h in history:
        role = "User" if h["role"] == "user" else "BA Agent"
        history_str += f"{role}: {h['text']}\n"
        if h["role"] == "user":
            user_turns_count += 1

    if user_turns_count >= 1:
        system_prompt = f"""
You are acting as an expert Business Analyst (BA) in a War Room interview.
Based on the requirement, recommend exactly which sub-agents from our team are needed (e.g. Product Owner, UI/UX Designer, Systems Architect, Lead Developer, QA Engineer).
Ask the user explicitly: "Please approve this list of agents to start the requirements alignment."
{kb_context}
"""
        prompt = f"Chat History:\n{history_str}\n\nUser New Input: {user_message}\n\nPlease recommend the final list of agents now."
        response_text = llm(system_prompt, prompt)
        return JSONResponse({
            "response": response_text,
            "requires_approval": True,
            "stage": "agent_list"
        })

    system_prompt = f"""
You are acting as an expert Business Analyst (BA).
The user wants to describe a requirement. Ask exactly 1 or 2 high-level multiple choice questions to establish the baseline requirement boundaries.
Keep it extremely simple. Do not ask detailed technical details or deep functional edge cases.
Always include "Other (please specify below)" as the final option.
{kb_context}
"""
    prompt = f"User requirement: {user_message}\n\nPlease ask 1-2 high-level baseline questions:"
    response_text = llm(system_prompt, prompt)
    return JSONResponse({
        "response": response_text,
        "requires_approval": False,
        "stage": "interview"
    })


# ============================================================
# AGENT DELEGATION / DISCUSSION SIMULATION ENDPOINT
# ============================================================

@app.post("/chat/simulate_agents")
async def simulate_agents(request: Request):
    body = await request.json()
    requirements_history = body.get("history", [])
    agent_name = body.get("agent_name", "Architect")
    knowledge_list = body.get("knowledge", [])
    artifacts_list = body.get("artifacts", [])
    
    kb_context = ""
    if knowledge_list:
        kb_context = "\nACTIVE KNOWLEDGE BASE REFERENCES:\n"
        for k in knowledge_list:
            kb_context += f"- Title: {k.get('title')}\n  Context: {k.get('content')}\n"

    req_summary = ""
    for h in requirements_history:
        role = "User" if h["role"] == "user" else "BA Agent"
        req_summary += f"{role}: {h['text']}\n"

    artifacts_str = ", ".join(artifacts_list) if artifacts_list else "selected documents"

    system_prompt = f"""
You are simulating a design room chat. You are the **{agent_name}**.
You are discussing with the lead **Business Analyst (BA)** to finalize the plan for the following requested artifacts: {artifacts_str}.

Provide 2-4 concrete, specific contribution points from your role's expertise that MUST be reflected in the final generated documents.
Each point must be a specific requirement, constraint, edge case, or decision grounded in the actual requirement discussed below — not generic boilerplate advice.
Format as short bullet points prefixed with "-". Keep the tone conversational in the intro line, but the bullet points must be concrete enough that a document writer could act on them directly.
If any selected document is a 'Process Flow Diagram' or 'System Architecture Specification', mention that we will use Miro to design the flow.
{kb_context}
"""

    prompt = f"Requirements history:\n{req_summary}\n\nPlease share your perspective as the {agent_name}:"
    response_text = llm(system_prompt, prompt)
    return JSONResponse({"transcript": response_text})


# ============================================================
# ARTIFACT GENERATION ENDPOINT
# ============================================================

@app.post("/chat/generate_artifacts")
async def generate_artifacts(request: Request):
    body = await request.json()
    requirements_history = body.get("history", [])
    knowledge_list = body.get("knowledge", [])
    artifacts_requested = body.get("artifacts", [])
    agent_contributions = body.get("agent_contributions", [])

    if not artifacts_requested:
        artifacts_requested = ["Business Requirements Document (BRD)", "System Architecture Spec", "Validation Test Scripts (UAT)"]

    kb_context = ""
    if knowledge_list:
        kb_context = "\nACTIVE KNOWLEDGE BASE REFERENCES:\n"
        for k in knowledge_list:
            kb_context += f"- Title: {k.get('title')}\n  Context: {k.get('content')}\n"

    team_context = ""
    if agent_contributions:
        team_context = "\nTEAM INPUT FROM SPECIALIST AGENTS (these points MUST be reflected in the generated documents where relevant to that document's scope):\n"
        for c in agent_contributions:
            team_context += f"\n--- {c.get('agent', 'Team Member')} ---\n{c.get('text', '')}\n"

    req_summary = ""
    for h in requirements_history:
        role = "User" if h["role"] == "user" else "BA Agent"
        req_summary += f"{role}: {h['text']}\n"

    # Prepend knowledge base and specialist team context to requirements summary
    if kb_context:
        req_summary = kb_context + "\n" + req_summary
    if team_context:
        req_summary = team_context + "\n" + req_summary

    files_list = []
    test_scripts_list = []
    recommended_stories = []

    # 1. Generate Business Requirements Document (BRD)
    if "Business Requirements Document (BRD)" in artifacts_requested:
        brd_sys = "You are a Business Analyst. Generate a detailed Business Requirements Document (BRD) in Markdown format. Structure: 1. Executive Summary, 2. Scope, 3. Functional Requirements, 4. Non-Functional Requirements, 5. User Stories."
        brd_content = llm(brd_sys, req_summary)
        # Save as Markdown
        with open(os.path.join(WORKSPACE_DIR, "BRD.md"), "w", encoding="utf-8") as f:
            f.write(brd_content)
        # Save as DOCX
        docx_brd_path = os.path.join(WORKSPACE_DIR, "BRD.docx")
        save_as_docx("Business Requirements Document (BRD)", brd_content, docx_brd_path)
        files_list.append({"name": "BRD.docx", "url": "/workspace/BRD.docx", "content": brd_content})

    # 2. Generate Functional Requirements Specification (FRS)
    if "Functional Requirements Specification (FRS)" in artifacts_requested:
        frs_sys = "You are a Functional Analyst. Generate a detailed Functional Requirements Specification (FRS) including system behaviors, error handling, and state transitions."
        frs_content = llm(frs_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "Functional_Requirements.md"), "w", encoding="utf-8") as f:
            f.write(frs_content)
        docx_frs_path = os.path.join(WORKSPACE_DIR, "Functional_Requirements.docx")
        save_as_docx("Functional Requirements Specification (FRS)", frs_content, docx_frs_path)
        files_list.append({"name": "Functional_Requirements.docx", "url": "/workspace/Functional_Requirements.docx", "content": frs_content})

    # 3. Generate Use Case Specification
    if "Use Case Specification" in artifacts_requested:
        uc_sys = "You are a Business Analyst. Generate a set of detailed Use Case Specifications including primary path, alternate paths, pre-conditions, and post-conditions."
        uc_content = llm(uc_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "Use_Cases.md"), "w", encoding="utf-8") as f:
            f.write(uc_content)
        docx_uc_path = os.path.join(WORKSPACE_DIR, "Use_Cases.docx")
        save_as_docx("Use Case Specification", uc_content, docx_uc_path)
        files_list.append({"name": "Use_Cases.docx", "url": "/workspace/Use_Cases.docx", "content": uc_content})

    # 4. Generate Process Flow Diagram (Miro-designed)
    if "Process Flow Diagram (Miro-designed)" in artifacts_requested:
        miro_token = os.getenv("MIRO_ACCESS_TOKEN", "eyJhbGciOiJIUzI1NiJ9.test_token")
        
        # 4a. Generate Word doc contents
        flow_sys = "You are a UI/UX Designer and Systems Analyst. Generate a detailed user journey and process flow specification including touchpoints, actions, and system responses."
        flow_content = llm(flow_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "Process_Flow_Diagram.md"), "w", encoding="utf-8") as f:
            f.write(flow_content)
        docx_flow_path = os.path.join(WORKSPACE_DIR, "Process_Flow_Diagram.docx")
        save_as_docx("Process Flow Diagram Specification", flow_content, docx_flow_path)
        files_list.append({"name": "Process_Flow_Diagram.docx", "url": "/workspace/Process_Flow_Diagram.docx", "content": flow_content})

        # 4b. Parse structured flowchart steps for Miro
        flow_json_sys = """
You are a UI/UX Designer and Systems Analyst. Analyze the requirements history and generate the key flowchart steps for the user login and dashboard journey.
Format the output EXACTLY as a JSON array of objects (with no extra markdown styling or backticks):
[
  {"title": "Step 1 Title", "text": "Description of step 1"},
  {"title": "Step 2 Title", "text": "Description of step 2"},
  ...
]
"""
        steps_raw = llm(flow_json_sys, req_summary)
        clean_steps_json = steps_raw.replace("```json", "").replace("```", "").strip()
        flow_steps = []
        try:
            flow_steps = json.loads(clean_steps_json)
        except Exception:
            flow_steps = [
                {"title": "Phase 1: Landing Page", "text": "User arrives at landing page; enters Username and Password."},
                {"title": "Phase 2: Authentication Check", "text": "System checks credentials and logs attempt with timestamp and IP address."},
                {"title": "Phase 3: Conditional OTP", "text": "Unrecognized device/IP triggers SMS/Email OTP code requirement."},
                {"title": "Phase 4: Mandatory MFA", "text": "User completes MFA check (authenticator app or push notification)."},
                {"title": "Phase 5: Secure Dashboard", "text": "Session established. User redirected to dashboard with masked account numbers."}
            ]

        # 4c. Create flowchart on Miro board
        miro_board_url = create_miro_flowchart(miro_token, "Online Banking Process Flow Map", flow_steps)
        files_list.append({"name": "Miro Process Flow Board (Interactive)", "url": miro_board_url, "external": True})

        # 4d. Generate Mermaid visual flow HTML page
        flow_mermaid_sys = """
You are a Systems Analyst. Generate a valid Mermaid flowchart syntax representing the login and OTP verification process.
Only return the Mermaid syntax inside a standard ```mermaid block.
Example:
```mermaid
graph TD
    A[Start] --> B[End]
```
"""
        flow_mermaid_raw = llm(flow_mermaid_sys, req_summary)
        mermaid_code = "graph TD\n    A[Start] --> B[End]"
        match = re.search(r"```mermaid\s*([\s\S]+?)\s*```", flow_mermaid_raw)
        if match:
            mermaid_code = match.group(1).strip()
        else:
            # Fallback simple flowchart syntax if matching failed
            mermaid_code = """graph TD
    Start[User arrives at Landing Page] --> Credentials[Enter Username & Password]
    Credentials --> LogAttempt[Log attempt in Audit DB]
    LogAttempt --> DeviceCheck{Unrecognized Device/IP?}
    DeviceCheck -- Yes --> OTP[Prompt SMS/Email OTP]
    OTP --> VerifyOTP[Verify OTP code]
    VerifyOTP --> MFA[Mandatory MFA challenge]
    DeviceCheck -- No --> MFA
    MFA --> Dashboard[Redirect to Dashboard with Masked Accounts]"""

        html_diagram_content = f"""<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
    <style>
        body {{
            background: #0b0f19;
            color: #e2e8f0;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
        }}
        .card {{
            background: #151f32;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 95%;
            width: 800px;
            box-sizing: border-box;
        }}
        h2 {{
            margin-top: 0;
            font-size: 18px;
            font-weight: 700;
            color: #10b981;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Interactive Process Flow Diagram</h2>
        <div class="mermaid">
            {mermaid_code}
        </div>
    </div>
</body>
</html>
"""
        with open(os.path.join(WORKSPACE_DIR, "Process_Flow_Visualization.html"), "w", encoding="utf-8") as f:
            f.write(html_diagram_content)
        files_list.append({"name": "Process_Flow_Visualization.html (Visual Diagram)", "url": "/workspace/Process_Flow_Visualization.html"})

    # 5. Generate System Architecture Specification (Miro-designed)
    if "System Architecture Specification (Miro-designed)" in artifacts_requested or "System Architecture Spec" in artifacts_requested:
        miro_token = os.getenv("MIRO_ACCESS_TOKEN", "eyJhbGciOiJIUzI1NiJ9.test_token")
        
        arch_sys = """You are a Systems Architect. Generate a System Design and Architecture document.
Include a valid Mermaid diagram (inside standard markdown ```mermaid blocks) representing the authentication and backend service flows.
Make the diagram thorough and descriptive."""
        arch_content = llm(arch_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "System_Architecture.md"), "w", encoding="utf-8") as f:
            f.write(arch_content)

        docx_arch_path = os.path.join(WORKSPACE_DIR, "System_Architecture.docx")
        save_as_docx("System Architecture Specification", arch_content, docx_arch_path)
        files_list.append({"name": "System_Architecture.docx", "url": "/workspace/System_Architecture.docx", "content": arch_content})

        # 5b. Create Miro flowchart for System Architecture
        arch_steps = [
            {"title": "UI Tier (Web Browser)", "text": "Renders user dashboard and interfaces. Initiates authentication requests."},
            {"title": "API Gateway / Guard", "text": "Filters traffic, handles SSL termination, and routes requests to services."},
            {"title": "Auth Microservice", "text": "Verifies credentials, checks password expiration, and manages sessions."},
            {"title": "MFA Engine", "text": "Orchestrates TOTP codes, conditional device OTP codes, and push validations."},
            {"title": "Audit Logger & DB", "text": "Logs all events (IP, timestamp, status) to high-availability database cluster."}
        ]
        miro_arch_url = create_miro_flowchart(miro_token, "Online Banking System Architecture Map", arch_steps)
        files_list.append({"name": "Miro System Architecture Board (Interactive)", "url": miro_arch_url, "external": True})

        # 5c. Extract Mermaid flow to create an HTML interactive renderer page
        mermaid_code = "graph TD\n    A[Start] --> B[End]"
        match = re.search(r"```mermaid\s*([\s\S]+?)\s*```", arch_content)
        if match:
            mermaid_code = match.group(1).strip()

        html_diagram_content = f"""<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
    <style>
        body {{
            background: #0b0f19;
            color: #e2e8f0;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
        }}
        .card {{
            background: #151f32;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 95%;
            width: 800px;
            box-sizing: border-box;
        }}
        h2 {{
            margin-top: 0;
            font-size: 18px;
            font-weight: 700;
            color: #3b82f6;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Interactive System Process Flow Diagram</h2>
        <div class="mermaid">
            {mermaid_code}
        </div>
    </div>
</body>
</html>
"""
        with open(os.path.join(WORKSPACE_DIR, "Interactive_Process_Flow.html"), "w", encoding="utf-8") as f:
            f.write(html_diagram_content)
        files_list.append({"name": "Interactive_Process_Flow.html (Visual Diagram)", "url": "/workspace/Interactive_Process_Flow.html"})

    # 6. Generate Validation Test Scripts (UAT)
    if "Validation Test Scripts (UAT)" in artifacts_requested or "Validation Test Scripts (manual & automated cases)" in artifacts_requested:
        test_sys = "You are a QA Engineer. Generate a comprehensive validation Test Script in Markdown. Include columns for Test Case ID, Description, Steps, Expected Result, and Status."
        test_content = llm(test_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "Test_Scripts.md"), "w", encoding="utf-8") as f:
            f.write(test_content)

        docx_test_path = os.path.join(WORKSPACE_DIR, "Test_Scripts.docx")
        save_as_docx("Validation Test Scripts", test_content, docx_test_path)
        test_scripts_list.append({"name": "Test_Scripts.docx", "url": "/workspace/Test_Scripts.docx", "content": test_content})
        files_list.append({"name": "Test_Scripts.docx", "url": "/workspace/Test_Scripts.docx", "content": test_content})

    # 7. Generate User Story Map & Sprint Backlog
    if "User Story Map & Sprint Backlog" in artifacts_requested or "User Story Map" in artifacts_requested:
        stories_sys = """
You are a Product Owner. Generate a list of recommended User Stories, tasks, and subtasks to push to Jira based on the final requirements.
Format the output EXACTLY as a JSON array of objects, with no extra markdown styling or backticks:
[
  {"summary": "Story summary", "issuetype": "Story", "description": "Story description", "priority": "Medium"},
  {"summary": "Task summary", "issuetype": "Task", "description": "Task description", "priority": "High"},
  {"summary": "Subtask summary", "issuetype": "Subtask", "description": "Subtask description", "priority": "Low"}
]
"""
        stories_content_raw = llm(stories_sys, req_summary)
        clean_json = stories_content_raw.replace("```json", "").replace("```", "").strip()
        try:
            recommended_stories = json.loads(clean_json)
        except Exception:
            pass

        # Write a user stories docx file and add to files_list
        stories_docx_sys = "You are a Product Owner. Generate a detailed User Story Map & Sprint Backlog with User Stories, Tasks, and Acceptance Criteria in Markdown."
        stories_docx_content = llm(stories_docx_sys, req_summary)
        with open(os.path.join(WORKSPACE_DIR, "User_Stories.md"), "w", encoding="utf-8") as f:
            f.write(stories_docx_content)
        docx_stories_path = os.path.join(WORKSPACE_DIR, "User_Stories.docx")
        save_as_docx("User Story Map & Sprint Backlog", stories_docx_content, docx_stories_path)
        files_list.append({"name": "User_Stories.docx", "url": "/workspace/User_Stories.docx", "content": stories_docx_content})

    if not recommended_stories:
        recommended_stories = [
            {"summary": "Implement login MFA component", "issuetype": "Story", "description": "As a customer, I want to authenticate securely via SMS/Email OTP.", "priority": "High"},
            {"summary": "Add real-time transaction balance validation", "issuetype": "Task", "description": "Validate source account funds prior to transfer execution.", "priority": "High"},
            {"summary": "Configure system transaction audit logging", "issuetype": "Task", "description": "Log all transaction attempts to database.", "priority": "Medium"}
        ]

    return JSONResponse({
        "success": True,
        "files": files_list,
        "test_scripts": test_scripts_list,
        "recommended_stories": recommended_stories
    })


# ============================================================
# CREATE MULTIPLE JIRA ISSUES ENDPOINT
# ============================================================

@app.post("/jira/create_bulk")
async def jira_create_bulk(request: Request):
    if not jira_configured():
        return JSONResponse({"error": "Jira not configured"}, status_code=503)
    try:
        body = await request.json()
        issues_list = body.get("issues", [])
        
        headers, auth = jira_headers()
        created_keys = []
        
        for item in issues_list:
            payload = {
                "fields": {
                    "project": {"key": JIRA_PROJECT_KEY},
                    "summary": item.get("summary", "New Item"),
                    "issuetype": {"name": item.get("issuetype", "Task")},
                }
            }
            desc = item.get("description", "")
            if desc:
                payload["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": desc}]}]
                }
            priority = item.get("priority", "")
            if priority:
                payload["fields"]["priority"] = {"name": priority}

            kwargs = {"headers": headers, "json": payload, "verify": JIRA_SSL_VERIFY, "timeout": 15}
            if auth:
                kwargs["auth"] = auth

            r = requests.post(f"{JIRA_URL}/rest/api/3/issue", **kwargs)
            if r.status_code in (200, 201):
                created_keys.append(r.json().get("key"))
        
        return JSONResponse({"success": True, "created": created_keys})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================
# CONFLUENCE INTEGRATION
# ============================================================

@app.post("/confluence/publish")
async def confluence_publish(request: Request):
    """
    Publishes a generated document directly to Confluence as a wiki page.
    If `content` is provided in the request body, that is published as-is
    (used when the caller drags a specific artifact over). Otherwise falls
    back to the BRD on disk for backward compatibility.
    """
    if not jira_configured():
        return JSONResponse({"error": "Atlassian credentials not configured"}, status_code=503)
    try:
        body = await request.json()
        title = body.get("title", "Banking Deposit page BRD")
        content = body.get("content")

        if content is None:
            brd_path = os.path.join(WORKSPACE_DIR, "BRD.md")
            if os.path.exists(brd_path):
                with open(brd_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = "Requirements details not finalized."

        # Parse simple markdown to Confluence Storage HTML format
        html_content = content.replace("\n", "<br>").replace("### ", "<h3>").replace("## ", "<h2>").replace("# ", "<h1>")

        headers, auth = jira_headers()
        space_key = JIRA_PROJECT_KEY

        # 1. Resolve the space key to the numeric space ID the v2 API requires
        get_kwargs = {"headers": headers, "params": {"keys": space_key}, "verify": JIRA_SSL_VERIFY, "timeout": 15}
        if auth:
            get_kwargs["auth"] = auth
        space_r = requests.get(f"{JIRA_URL}/wiki/api/v2/spaces", **get_kwargs)
        space_results = space_r.json().get("results", []) if space_r.status_code == 200 else []
        if not space_results:
            return JSONResponse({"success": False, "error": f"No Confluence space found with key '{space_key}'. Create a space with that key first."})
        space_id = space_results[0]["id"]

        payload = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": f"<p>{html_content}</p>"
            }
        }

        kwargs = {"headers": headers, "json": payload, "verify": JIRA_SSL_VERIFY, "timeout": 15}
        if auth:
            kwargs["auth"] = auth

        # 2. Create the page via confluence REST v2 API
        r = requests.post(f"{JIRA_URL}/wiki/api/v2/pages", **kwargs)
        if r.status_code in (200, 201):
            page_id = r.json().get("id")
            page_url = f"{JIRA_URL}/wiki/spaces/{space_key}/pages/{page_id}"
            return JSONResponse({"success": True, "url": page_url})
        else:
            return JSONResponse({"success": False, "error": r.text})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ============================================================
# MIRO INTEGRATION
# ============================================================

@app.post("/miro/sync_board")
async def miro_sync_board(request: Request):
    """
    Creates a new Miro board and maps the user stories as visual Sticky Notes.
    """
    miro_token = os.getenv("MIRO_ACCESS_TOKEN", "eyJhbGciOiJIUzI1NiJ9.test_token")
    try:
        body = await request.json()
        board_name = body.get("name", "Requirements Mapping Board")
        stories = body.get("stories", [])
        
        headers = {
            "Authorization": f"Bearer {miro_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 1. Create Board
        board_payload = {
            "name": board_name,
            "description": "Visual requirements user story map generated by BA Suite."
        }
        r_board = requests.post("https://api.miro.com/v2/boards", headers=headers, json=board_payload, timeout=10)
        
        if r_board.status_code not in (200, 201):
            # If token is default/invalid, simulate a successful mock board creation response with a Miro demo link
            mock_url = "https://miro.com/app/board/uXjVPkMck5Q=/"
            return JSONResponse({"success": True, "simulated": True, "url": mock_url})

        board_id = r_board.json().get("id")
        board_url = r_board.json().get("viewLink")

        # 2. Add Sticky Notes for each story
        x_coord = 0
        for item in stories[:10]: # Limit to first 10
            sticky_payload = {
                "data": {
                    "content": f"<b>[{item.get('issuetype','Story')}]</b><br>{item.get('summary')}<br><small>{item.get('description','')}</small>"
                },
                "position": {
                    "x": x_coord,
                    "y": 0
                }
            }
            requests.post(f"https://api.miro.com/v2/boards/{board_id}/items", headers=headers, json=sticky_payload, timeout=5)
            x_coord += 250 # Offset positions horizontally
            
        return JSONResponse({"success": True, "url": board_url})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ============================================================
# CORE GET ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/artifacts/recover")
async def artifacts_recover():
    """
    Rebuilds an artifact manifest from whatever .docx/.html files already
    exist on disk in WORKSPACE_DIR. Used to recover a project's Artifacts
    tab when the browser's saved manifest was lost (e.g. generated before
    client-side persistence was added). Reads the matching .md sidecar
    (same base filename) as the document's viewable/draggable content when
    present. Miro board links cannot be recovered this way since they are
    never written to disk.
    """
    files_list = []
    if os.path.isdir(WORKSPACE_DIR):
        for fname in sorted(os.listdir(WORKSPACE_DIR)):
            base, ext = os.path.splitext(fname)
            if ext == ".docx":
                entry = {"name": fname, "url": f"/workspace/{fname}"}
                md_path = os.path.join(WORKSPACE_DIR, base + ".md")
                if os.path.exists(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        entry["content"] = f.read()
                files_list.append(entry)
            elif ext == ".html":
                files_list.append({"name": f"{fname} (Visual Diagram)", "url": f"/workspace/{fname}"})
    return JSONResponse({"success": True, "files": files_list})

@app.get("/jira/status")
async def jira_status():
    if not jira_configured():
        return JSONResponse({"connected": False, "error": "Not configured"})
    try:
        headers, auth = jira_headers()
        kwargs = {"headers": headers, "verify": JIRA_SSL_VERIFY, "timeout": 8}
        if auth:
            kwargs["auth"] = auth
        r = requests.get(f"{JIRA_URL}/rest/api/3/myself", **kwargs)
        if r.status_code == 200:
            return JSONResponse({"connected": True, "project": JIRA_PROJECT_KEY, "jira_url": JIRA_URL})
        return JSONResponse({"connected": False})
    except Exception:
        return JSONResponse({"connected": False})

@app.get("/jira/issues")
async def jira_issues(status: str = "all", max_results: int = 50):
    if not jira_configured():
        return JSONResponse({"error": "Jira not configured"}, status_code=503)
    try:
        headers, auth = jira_headers()
        jql = f"project = {JIRA_PROJECT_KEY} ORDER BY updated DESC"
        params = {"jql": jql, "maxResults": max_results, "fields": "summary,status,assignee,priority,issuetype,url"}
        kwargs = {"headers": headers, "params": params, "verify": JIRA_SSL_VERIFY, "timeout": 15}
        if auth:
            kwargs["auth"] = auth
        r = requests.get(f"{JIRA_URL}/rest/api/3/search/jql", **kwargs)
        r.raise_for_status()
        data = r.json()
        issues = []
        for issue in data.get("issues", []):
            f = issue.get("fields", {})
            status_obj = f.get("status", {})
            issues.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": status_obj.get("name", "Unknown"),
                "priority": (f.get("priority") or {}).get("name", "Medium"),
                "issueType": (f.get("issuetype") or {}).get("name", "Task"),
                "url": f"{JIRA_URL}/browse/{issue['key']}",
            })
        return JSONResponse({"issues": issues})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
