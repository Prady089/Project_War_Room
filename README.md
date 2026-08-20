# Project War Room: High-Agency Software Synthesis Factory

![Project War Room Architecture]
Project War Room is a state-of-the-art, multi-agent AI framework designed to bridge the gap between human requirements and production-ready software. By orchestrating a fleet of specialized neural agents, Project War Room automates the entire Software Development Life Cycle (SDLC) in real-time.


In this example, Agents are asked to create simple calcaulator web application.
<img width="1919" height="868" alt="image" src="https://github.com/user-attachments/assets/92381d24-edf0-4b58-9f43-9f3e556acdab" />

Conversation / work handoff between agent

USER INTENT
Create a calculator web application

PROJECT WAR ROOM
📁 Project workspace created: workspace/Create_a_calculator_web_application/

BUSINESS ANALYST
Request received.
BRD summary:
- Develop a web-based calculator application.
- Ensure the application supports basic arithmetic operations: addition, subtraction, multiplication, and division.
- Design a user-friendly interface for both desktop and mobile devices.
Next: System Architect to design the system.
description
business_requirements.md

SYSTEM ARCHITECT
Architecture complete.
Design summary:
- **Decision 1**: Use a single-page application (SPA) framework, such as React.js, to ensure a responsive and dynamic user interface.
- **Decision 2**: Implement a client-side logic for arithmetic operations to reduce server load and improve performance.
- **Decision 3**: Employ CSS media queries and a flexible grid layout to achieve a responsive design compatible with various devices.
Next: Developer to implement the build.
description
architecture_design.md

DEVELOPER
Build shipped.
Implementation summary:
- index.html: Basic structure with buttons for digits and operations, and a display area.
- style.css: Dark theme with CSS variables for colors, responsive layout using flexbox.
- script.js: Handles arithmetic operations and updates display; checks for division by zero.
description
index.html
description
style.css
description
script.js

QA ENGINEER
Audit complete.
Findings:
- Issue 1: The calculator does not handle decimal numbers, which limits its functionality for more precise calculations.
- Issue 2: There is no validation for consecutive operators, potentially causing logical errors in calculations.
- Issue 3: The CSS lacks focus styles for accessibility, which is necessary for keyboard navigation users.
Verdict: Needs Revision.
Next: Developer to revise.
description
qa_audit.md

QA ROUTER
Revision required. Issues to fix:
- Issue 1: The calculator does not handle decimal numbers, which limits its functionality for more precise calculations.
- Issue 2: There is no validation for consecutive operators, potentially causing logical errors in calculations.
- Issue 3: The CSS lacks focus styles for accessibility, which is necessary for keyboard navigation users.

DEVELOPER
Revision applied and resubmitted.
Implementation summary:
- index.html: Added a decimal point button.
- style.css: Added focus styles for accessibility.
- script.js: Added support for decimal numbers and validation for consecutive operators.
Next: QA to audit.
description
index.html
description
style.css
description
script.js

QA ENGINEER
Audit complete.
Findings:
- Issue 1: None
- Issue 2: None
- Issue 3: None
Verdict: Approved.
Next: Proceed with deployment.
description
qa_audit.md
RELEASE MANAGER
Release complete
Project: Create_a_calculator_web_application
Location: workspace/Create_a_calculator_web_application/
Revisions completed: 1
Preview ready in the right panel.




## 🌌 The Vision
Unlike traditional LLM wrappers, **Project War Room** operates as a high-agency "factory." It doesn't just answer questions; it **synthesizes artifacts**. From requirements gathering to architectural design and final QA auditing, every step is handled by a specialized agent working in a synchronized neural loop.

## 🤖 The Neural Fleet
The interface features a proprietary "Zig-Zag" formation that represents the logical flow of a professional software agency:

| Agent | Icon | Responsibility |
| :--- | :---: | :--- |
| **Planner** | 🧠 | Analyzes intent, maps objectives, and orchestrates the neural pathway. |
| **BA** | 📐 | Business Analyst: Extracts constraints, defines features, and creates the SRS. |
| **Architect** | 🕸️ | System Architect: Designs folder structures, tech stacks, and modular logic. |
| **Developer** | 🧶 | The Weaver: Synthesizes clean, high-performance source code into live artifacts. |
| **QA** | 🛡️ | Sentry: Audits logic, performs edge-case validation, and signs off on the build. |

## 🚀 Key Features
*   **Cyber-Organic Workspace**: A premium glassmorphic UI featuring active-node lighting and fluid circular animations.
*   **Live Projection Tile**: A localized "holographic" preview area that renders build artifacts (HTML/CSS/JS) the moment they are generated.
*   **Multi-Agent Context Flow**: Agents "communicate" through an internal history stream, allowing for complex, multi-file software projects.
*   **Refinement Loop**: Iteratively refine your software by chatting directly with the fleet—agents adapt existing code based on new feedback.
*   **Artifact-Centric**: Every agent output is a real file saved to your workspace, ensuring the factory produces tangible value.

## 🛠 Technical Architecture
*   **Model**: Powered by **Google Gemini 2.0 Flash** (Model of choice for speed and high-context reasoning).
*   **Backend**: A high-performance **FastAPI** hub managing synchronized event streams.
*   **UI/UX**: **Gradio** for logic orchestration combined with a custom **Tailwind CSS** frontend for a futuristic aesthetic.
*   **Design System**: Utilizes **Orbitron**, **Outfit**, and **Fira Code** for a futuristic, developer-focused experience.

## ⚡ Setup & Execution

### Prerequisites
*   Python 3.10+
*   Google Gemini API Key

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/Prady089/Project_War_Room.git
   cd Project_War_Room
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure your API key in `server.py` and `app.py`.

### Running the Factory
The system requires two processes:
1.  **Launch the Backend Core**:
    ```bash
    python server.py
    ```
2.  **Launch the Synthesis Interface**:
    ```bash
    python app.py
    ```
3.  **Access the Hub**:
    *   **Project War Room Hub**: `http://localhost:8003`
    *   **Internal Synthesis Engine**: `http://127.0.0.1:7860`

## 👨‍💻 Author
**Pradeep Kumar**
[LinkedIn Profile](https://www.linkedin.com/in/prady089/)

---
*Project War Room - Orchestrating the future of agentic development.*
