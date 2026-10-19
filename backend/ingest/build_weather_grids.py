"""기상청 가이드의 격자_위경도 엑셀에서 제주 읍면동 격자만 뽑아 data/jeju_grids.json을 만든다."""
import argparse
import json
import logging
from pathlib import Path

import openpyxl

from config import get_settings, setup_logging

logger = logging.getLogger(__name__)

JEJU_CODE_PREFIX = "50"  # 행정구역코드 앞 두 자리: 제주특별자치도


def extract_jeju_grids(xlsx: Path) -> list[dict[str, object]]:
    """엑셀에서 제주의 읍면동(3단계) 행을 {city, name, nx, ny, lat, lng}로 뽑는다."""
    ws = openpyxl.load_workbook(xlsx, read_only=True).worksheets[0]
    rows = ws.iter_rows(min_row=2, values_only=True)
    grids: list[dict[str, object]] = []
    for r in rows:
        code, city, name, nx, ny, lng, lat = r[1], r[3], r[4], r[5], r[6], r[13], r[14]
        if not str(code or "").startswith(JEJU_CODE_PREFIX) or not name or not nx or not lng:
            continue
        grids.append({"city": city, "name": name, "nx": int(nx), "ny": int(ny), "lat": round(float(lat), 5), "lng": round(float(lng), 5)})
    return grids


def main() -> None:
    """엑셀 경로를 받아 제주 격자 목록을 저장한다."""
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    args = parser.parse_args()
    grids = extract_jeju_grids(args.xlsx)
    out = get_settings().data_dir / "jeju_grids.json"
    out.write_text(json.dumps(grids, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("제주 읍면동 %d곳, 서로 다른 격자 %d개 저장: %s", len(grids), len({(g["nx"], g["ny"]) for g in grids}), out)


if __name__ == "__main__":
    main()
