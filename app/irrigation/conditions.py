from datetime import datetime


def evaluate_program(
    program,
    now: datetime,
    soil_humidity: float | None,
    ambient_temp: float | None,
) -> bool:
    conditions = program.conditions or []
    if not conditions:
        return False

    logic = program.condition_logic  # "AND" | "OR"
    results = [_eval_condition(c, now, soil_humidity, ambient_temp) for c in conditions]

    return any(results) if logic == "OR" else all(results)


def _eval_condition(
    condition: dict,
    now: datetime,
    soil_humidity: float | None,
    ambient_temp: float | None,
) -> bool:
    ctype = condition.get("type")
    if ctype == "schedule":
        return _eval_schedule(condition, now)
    if ctype == "soil_humidity":
        return _eval_comparison(condition, soil_humidity)
    if ctype == "temperature":
        return _eval_comparison(condition, ambient_temp)
    if ctype == "time_range":
        return _eval_time_range(condition, now)
    return False


def _eval_schedule(condition: dict, now: datetime) -> bool:
    try:
        h, m = map(int, condition["time"].split(":"))
    except (KeyError, ValueError):
        return False
    days = condition.get("days", list(range(1, 8)))
    return now.isoweekday() in days and now.hour == h and now.minute == m


def _eval_comparison(condition: dict, value: float | None) -> bool:
    if value is None:
        return False
    op = condition.get("operator")
    threshold = condition.get("value")
    if threshold is None:
        return False
    if op == "lt":
        return value < threshold
    if op == "gt":
        return value > threshold
    return False


def _eval_time_range(condition: dict, now: datetime) -> bool:
    try:
        from_h, from_m = map(int, condition["from"].split(":"))
        to_h, to_m = map(int, condition["to"].split(":"))
    except (KeyError, ValueError):
        return False

    now_mins = now.hour * 60 + now.minute
    from_mins = from_h * 60 + from_m
    to_mins = to_h * 60 + to_m

    if from_mins <= to_mins:
        return from_mins <= now_mins < to_mins
    else:  # overnight range (e.g. 22:00 → 06:00)
        return now_mins >= from_mins or now_mins < to_mins
