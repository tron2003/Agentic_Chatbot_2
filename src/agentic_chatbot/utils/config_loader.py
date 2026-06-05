import yaml


def load_mcp_config(path: str):
    with open(path, "r") as f:
        return yaml.safe_load(f)