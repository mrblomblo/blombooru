import argparse
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    if args.debug:
        os.environ["BLOMBOORU_DEBUG"] = "true"

    from backend.app.utils.logger import logger
    logger.info("Starting Blombooru" + (" with debug mode enabled" if args.debug else ""))

    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=args.debug,
        log_config=None,
    )
