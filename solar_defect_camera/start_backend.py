import os

import uvicorn

from backend.main import load_local_env


if __name__ == "__main__":
    load_local_env()
    try:
        uvicorn.run(
            "backend.main:app",
            host=os.getenv("BACKEND_HOST", "0.0.0.0"),
            port=int(os.getenv("BACKEND_PORT", "8000")),
            reload=False,
            access_log=False,
            loop="asyncio",
        )
    except KeyboardInterrupt:
        pass
