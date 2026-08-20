import os, uuid, time, re, shutil
import gradio as gr
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# BRAND & DIRECTORY CONFIG
# ============================================================

BRAND_NAME = "PROJECT WAR ROOM"
TAGLINE = "High-Agency Software Synthesis"
AUTHOR = "PROJECT WAR ROOM"
AUTHOR_LINKEDIN = "#"
LOGO_PATH = "workspace/orbita_logo_cropped.png"

WORKSPACE_DIR = os.path.join(os.getcwd(), "workspace")
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)

# ============================================================
# GEMINI CONFIG
# ============================================================

genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))

def llm(system, user):
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=system + "\n\nImportant: Do not recite copyrighted material or training data verbatim. Be creative and synthesize new logic based on requirements."
        )
        response = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
            )
        )
        
        # Check for recitation block
        if hasattr(response, 'candidates') and response.candidates:
            if response.candidates[0].finish_reason == 4:
                return "AGENT ERROR: Recitation block (Finish Reason 4). The model detected it was copying known text too closely. Try re-phrasing your request."
        
        return response.text.strip()
    except Exception as e:
        return f"LLM_ERROR: {str(e)}"


def clean_list(text):
    return [a.strip() for a in text.split(",") if a.strip()]


# ============================================================
# UTILS: FILE EXTRACTION
# ============================================================

def extract_code_to_files(text):
    """
    Looks for pattern:
    ### FILE: filename.ext
    ```language
    code
    ```
    """
    pattern = r"### FILE:\s*([a-zA-Z0-9_\-\.]+)\n+```[a-z]*\n([\s\S]*?)```"
    matches = re.finditer(pattern, text)
    files_created = []
    
    for match in matches:
        filename = match.group(1).strip()
        content = match.group(2)
        
        # Ensure workspace exists
        if not os.path.exists(WORKSPACE_DIR):
            os.makedirs(WORKSPACE_DIR)
            
        file_path = os.path.join(WORKSPACE_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        files_created.append(filename)
        
    return files_created


# ============================================================
# PLANNER (SOFTWARE LIFECYCLE AWARE)
# ============================================================

PLANNER_PROMPT = """
You are the Lead Architect of the ORBITA Software Factory.
Your goal is to break down a software requirement into a standard SDLC workflow.

Roles to prioritize:
- Business Analyst (BA): Define requirements and features.
- System Architect: Design file structure and tech stack.
- Developer: Write the actual source code.
- QA Engineer: Test and validate the code.

Return EXACT format:

Personas:
1. <Role> - <Why>

Workflow:
2-4 sentences describing the development plan.

Linear_Workflow_Roles: <Role1>, <Role2>, <Role3>, <Role4>
"""


def planner(task):
    output = llm(PLANNER_PROMPT, f"TASK:\n{task}")
    roles = []
    for line in output.splitlines():
        if line.startswith("Linear_Workflow_Roles:"):
            roles = clean_list(line.split(":")[1])
    return output, roles


# ============================================================
# ROLE-LOCKED AGENT EXECUTION (HIGH AGENCY V2)
# ============================================================

def run_agent(task, agent, history):
    agent_lower = agent.lower()
    is_developer = "developer" in agent_lower or "coder" in agent_lower
    is_ba = "analyst" in agent_lower or "ba" in agent_lower
    is_qa = "qa" in agent_lower or "test" in agent_lower or "test" in agent_lower
    is_architect = "architect" in agent_lower or "design" in agent_lower

    system = f"""
You are acting STRICTLY as a {agent} in a high-speed Software Factory.

CORE PRINCIPLE: EVERYTHING MUST BE AN ARTIFACT.
- Do NOT just "talk" or give advice.
- You MUST provide your work as a digital artifact (a file).
- Use the format:
  ### FILE: filename.ext
  ```language
  content
  ```

ROLE CONSTRAINTS:
"""

    if is_ba:
        system += """
- Your goal: Create the 'business_requirements.md'.
- List user stories, features, and success criteria.
- Ensure the Developer knows EXACTLY what to build.
"""
    elif is_architect:
        system += """
- Your goal: Create the 'architecture_design.md'.
- Define the folder structure, data flow, and technology choices.
- Tell the Developer which libraries to use.
"""
    elif is_developer:
        system += """
- Your goal: Create the actual source code files.
- Read the 'business_requirements.md' and 'architecture_design.md' from history.
- Write full, working code only.
"""
    elif is_qa:
        system += """
- Your goal: Create 'qa_test_report.md' and 'test_suite.py'.
- CRITICALLY AUDIT the code written by the Developer in the history.
- List specific bugs or edge cases (e.g., empty inputs, negative numbers).
- If the code is perfect, sign off on it.
"""
    else:
        system += f"- Provide your contribution as a relevant file in the '### FILE: filename.ext' format."

    system += """
STYLE:
- Professional, technical, and artifact-focused.
- No emojis. No conversational filler like "I will now setup...". Just deliver the file.
"""

    recent_context = "\n".join(history.split("\n")[-20:])

    user = f"""
TASK: {task}

PREVIOUS WORK (Read this to ensure alignment):
{recent_context}

Now, deliver your specific artifact/file for this stage.
"""
    return llm(system, user)


def summarize(task, history):
    return llm(
        "You are the Release Manager. Summarize the developed application, list the files created in 'workspace/', and give run instructions.",
        f"TASK:\n{task}\n\nFULL CONTEXT:\n{history}"
    )


# ============================================================
# UI RENDERERS
# ============================================================

def render_chat(agent_log):
    html = """
    <style>
     .bubble {
      max-width:95%;
      padding:20px;
      margin:12px auto;
      border-radius:12px;
      white-space:pre-wrap;
      font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
      line-height: 1.6;
      color: #1e293b !important;
      border: 1px solid #e5e7eb;
    }
    .left { background:#ffffff; border-left: 6px solid #6366f1; }
    .right { background:#fefce8; border-left: 6px solid #f59e0b; }
    .center { background:#f5f3ff; text-align:center; font-weight:600; border: 1px solid #ddd6fe; margin: 30px auto; color: #4338ca !important; }
    .agent-header {
      font-size:11px;
      font-weight:800;
      color:#4f46e5;
      text-transform:uppercase;
      margin-bottom:10px;
      letter-spacing: 0.05em;
    }
    </style>
    """

    for idx, (agent, text) in enumerate(agent_log.items()):
        side = "center" if agent.lower() in ["planner", "summary"] else ("left" if idx % 2 == 0 else "right")
        
        html += f"""
        <div class="bubble {side}">
          <div class="agent-header">{agent}</div>
          <div>{text}</div>
        </div>
        """
    return html


# ============================================================
# CORE WORKFLOW
# ============================================================

def run_orbita_factory(task, agent_text):
    # 1. Plan
    planner_out, suggested_agents = planner(task)
    agents = clean_list(agent_text) if agent_text.strip() else suggested_agents

    log = {"Planner": planner_out}
    history = f"PLANNER:\n{planner_out}"
    all_files = []

    # 2. Execute Agents
    for agent in agents:
        log[agent] = f"<i>{agent} is processing...</i>"
        yield render_chat(log), log, "", f"Working: {agent}"

        output = run_agent(task, agent, history)
        
        # Extract files
        new_files = extract_code_to_files(output)
        all_files.extend(new_files)
        
        log[agent] = output
        history += f"\n\n{agent} OUTPUT:\n{output}"
        
        status = f"Files Generated: {', '.join(all_files)}" if all_files else f"Active: {agent}"
        yield render_chat(log), log, "", status

    # 3. Summarize
    summary = summarize(task, history)
    log["Summary"] = summary
    
    yield render_chat(log), log, summary, "✅ Deployment Complete"


# ============================================================
# UI (GRADIO)
# ============================================================

with gr.Blocks() as app:
    gr.HTML(f"""
    <div style="text-align: center; padding: 30px; background: #1e293b; color: white; border-radius: 12px; margin-bottom: 25px;">
        <h1 style="margin: 0; font-size: 2.2em; letter-spacing: -1px;">{BRAND_NAME}</h1>
        <p style="margin: 5px 0 0 0; color: #94a3b8; font-weight: 500;">{TAGLINE}</p>
    </div>
    """)

    with gr.Row():
        with gr.Column(scale=1):
            task_input = gr.Textbox(
                label="Product Requirement", 
                placeholder="e.g. Create a simple calculator app with a clean UI",
                lines=4
            )
            suggest_btn = gr.Button("📋 Generate Team Plan")
            agents_input = gr.Textbox(
                label="Project Roles",
                placeholder="Agents involved in development..."
            )
            run_btn = gr.Button("🚀 Start Factory", variant="primary")
            
            status_view = gr.Label(label="Live Factory Status", value="Ready")

        with gr.Column(scale=2):
            chat_output = gr.HTML(label="Factory Output")
            summary_output = gr.Textbox(label="Release Summary", lines=6)
            
    state_log = gr.State({})

    suggest_btn.click(lambda t: ", ".join(planner(t)[1]), task_input, agents_input)

    run_btn.click(
        run_orbita_factory,
        inputs=[task_input, agents_input],
        outputs=[chat_output, state_log, summary_output, status_view]
    )


if __name__ == "__main__":
    app.launch(theme=gr.themes.Default())
