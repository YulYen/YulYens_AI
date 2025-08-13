from pathlib import Path
import yaml
import uvicorn
from api.app import app

def load_api_cfg():
    data = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    api = data["api"]            # darf knallen, wenn fehlt
    if not api.get("enabled", False):
        raise RuntimeError("API disabled in config.yaml (api.enabled=false).")
    return api

def main():
    api = load_api_cfg()
    uvicorn.run(
        app,
        host=api["host"],
        port=int(api["port"]),
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
