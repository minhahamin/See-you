"""로컬 개발용: 내장 PostgreSQL을 띄우고 API 서버를 함께 실행한다.

DB 데이터는 홈 디렉터리의 ~/.seeyou/pgdata에 남아서 다시 실행해도 계정·대화가 유지된다.
(프로젝트 경로에 한글이 있으면 Windows에서 내장 Postgres 초기화가 실패하므로 ASCII 경로인 홈 아래에 둔다. PGDATA_DIR로 바꿀 수 있다.)
실행: backend/에서 `python -m scripts.dev_server [--port 8000] [--reload]`
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import pgserver
import uvicorn


logger = logging.getLogger(__name__)


def main() -> None:
    """내장 Postgres를 시작하고 DATABASE_URL을 설정한 뒤 uvicorn을 실행한다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    data_dir = Path(os.environ.get("PGDATA_DIR") or Path.home() / ".seeyou" / "pgdata")
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(data_dir, cleanup_mode="stop")
    os.environ["DATABASE_URL"] = server.get_uri()  # api.main을 가져오기 전에 설정해야 한다
    logging.basicConfig(level=logging.INFO)
    logger.info("내장 PostgreSQL 실행 중 (데이터: %s)", data_dir)
    try:
        # Windows의 uvicorn 기본 루프(Proactor)는 psycopg 비동기와 호환되지 않아 Selector 루프를 쓰게 한다 (리눅스에서는 기본 루프)
        loop = "agent.checkpoint:selector_loop_factory" if sys.platform == "win32" else "auto"
        uvicorn.run("api.main:app", host="127.0.0.1", port=args.port, reload=args.reload, loop=loop)
    finally:
        server.cleanup()


if __name__ == "__main__":
    main()
