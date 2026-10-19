"""일정 이동: 방문 하나를 다른 시간·일차로 옮기고 이동시간을 다시 계산한다. LLM 없이 규칙으로만 처리한다."""
import re

from agent import catalog
from agent.planning import SLOT_ORDER, SLOT_START_MIN, fmt_time, parse_time
from agent.state import DayPlan, Itinerary, Slot, Visit
from tools.route import travel_minutes

DAY_START_MIN = 8 * 60
DAY_END_MIN = 22 * 60

# 타임라인에서 끌어다 놓을 때 프론트가 보내는 문장: "1일차 2번째 방문(장소명)을 2일차 14:00로 옮겨줘"
MOVE_PATTERN = re.compile(r"(\d+)일차 (\d+)번째 방문\(.*\)을 (\d+)일차 (\d{1,2}:\d{2})로 옮겨줘")


class MoveError(Exception):
    """이동할 수 없는 요청. 메시지는 사용자에게 그대로 보여 준다."""


def parse_move(text: str) -> tuple[int, int, int, int] | None:
    """이동 문장이면 (원래 일차, 원래 순번(1부터), 도착 일차, 도착 시작 분)을 돌려준다."""
    m = MOVE_PATTERN.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), parse_time(m.group(4))


def _slot_for(start: int) -> Slot:
    """시작 시각에 가장 알맞은 하루 중 역할 (재배치할 때 순서가 어긋나지 않게 한다)."""
    fitting = [s for s in SLOT_ORDER if SLOT_START_MIN[s] <= start]
    return fitting[-1] if fitting else SLOT_ORDER[0]


def relayout(visits: list[Visit], starts: list[int]) -> list[Visit]:
    """순서대로 놓으면서 이동시간을 다시 계산하고, 앞 방문과 겹치면 뒤로 민다. 22시를 넘으면 MoveError."""
    all_places = catalog.places()
    result: list[Visit] = []
    cursor, prev = 0, None
    for visit, wanted in zip(visits, starts):
        place = all_places[visit.place_id]
        coord = (place.lat, place.lng)
        travel = travel_minutes(prev, coord) if prev else 0
        start = max(wanted, cursor + travel)
        end = start + (parse_time(visit.end) - parse_time(visit.start))
        if end > DAY_END_MIN:
            raise MoveError(f"{fmt_time(DAY_END_MIN)} 이후로 일정이 밀려서 옮길 수 없어요.")
        result.append(visit.model_copy(update={"start": fmt_time(start), "end": fmt_time(end), "travel_minutes_from_prev": travel}))
        cursor, prev = end, coord
    return result


def _day_by_number(itinerary: Itinerary, number: int) -> DayPlan:
    """일차 번호로 하루를 찾는다."""
    day = next((d for d in itinerary.days if d.day == number), None)
    if day is None:
        raise MoveError(f"{number}일차를 찾지 못했어요.")
    return day


def move_visit(itinerary: Itinerary, from_day: int, from_index: int, to_day: int, start: int) -> Itinerary:
    """방문을 to_day의 start(분)로 옮긴다. 옮긴 방문만 changed로 표시하고 나머지는 시각을 지키되 겹치면 뒤로 민다."""
    source, target = _day_by_number(itinerary, from_day), _day_by_number(itinerary, to_day)
    if not 1 <= from_index <= len(source.visits):
        raise MoveError("옮길 방문을 찾지 못했어요.")
    start = min(max(start, DAY_START_MIN), DAY_END_MIN)

    moving = source.visits[from_index - 1]
    duration = parse_time(moving.end) - parse_time(moving.start)
    moved = moving.model_copy(update={"start": fmt_time(start), "end": fmt_time(start + duration), "slot": _slot_for(start), "changed": True})

    cleared = {d.day: [v.model_copy(update={"changed": False}) for v in d.visits] for d in itinerary.days}
    cleared[from_day] = [v for i, v in enumerate(cleared[from_day], 1) if i != from_index]
    # 같은 시각에 놓이면 옮긴 방문을 먼저 둔다
    before = [v for v in cleared[to_day] if parse_time(v.start) < start]
    after = [v for v in cleared[to_day] if parse_time(v.start) >= start]
    cleared[to_day] = [*before, moved, *after]

    days = []
    for d in itinerary.days:
        if d.day not in (from_day, to_day):
            days.append(d.model_copy(update={"visits": cleared[d.day]}))
            continue
        visits = cleared[d.day]
        days.append(d.model_copy(update={"visits": relayout(visits, [parse_time(v.start) for v in visits])}))
    return itinerary.model_copy(update={"days": days})
