from pathlib import Path

project_name = "agentic_chatbot"

folders = [
    "config",

    f"src/{project_name}/constants",
    f"src/{project_name}/entity",
    f"src/{project_name}/config",
    f"src/{project_name}/components",
    f"src/{project_name}/pipelines",
    f"src/{project_name}/utils",
    f"src/{project_name}/logging",
    f"src/{project_name}/exception",
    f"src/{project_name}/prompts",

    "app/api",
    "app/frontend",
    "app/websocket",

    "research",
    "notebooks",
    "tests",
    "docker",
]

files = [
    "config/config.yaml",
    "config/schema.yaml",
    "config/params.yaml",

    f"src/{project_name}/__init__.py",

    f"src/{project_name}/config/configuration.py",

    f"src/{project_name}/entity/config_entity.py",
    f"src/{project_name}/entity/artifact_entity.py",

    f"src/{project_name}/components/ingestion.py",
    f"src/{project_name}/components/embedding.py",
    f"src/{project_name}/components/retriever.py",
    f"src/{project_name}/components/rag_pipeline.py",
    f"src/{project_name}/components/file_editor.py",
    f"src/{project_name}/components/tool_router.py",
    f"src/{project_name}/components/llm_loader.py",

    f"src/{project_name}/pipelines/training_pipeline.py",
    f"src/{project_name}/pipelines/rag_pipeline.py",
    f"src/{project_name}/pipelines/agent_pipeline.py",
    f"src/{project_name}/pipelines/inference_pipeline.py",

    f"src/{project_name}/utils/common.py",

    f"src/{project_name}/logging/logger.py",

    f"src/{project_name}/exception/__init__.py",

    f"src/{project_name}/prompts/planner_prompt.txt",
    f"src/{project_name}/prompts/rag_prompt.txt",
    f"src/{project_name}/prompts/file_editor_prompt.txt",
    f"src/{project_name}/prompts/router_prompt.txt",

    "app/main.py",

    "requirements.txt",
    "setup.py",
    ".env",
    ".gitignore",
    "README.md",
]

for folder in folders:
    Path(folder).mkdir(parents=True, exist_ok=True)

for file in files:
    file_path = Path(file)

    if not file_path.exists():
        file_path.touch()

print("Project structure created successfully.")