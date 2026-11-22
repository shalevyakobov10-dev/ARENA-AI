"""בוני סדרות מחירים לסימולציות בטסטים."""


def trending_series(start: float = 0.30, end: float = 0.75, n: int = 120, wiggle: float = 0.004) -> list[float]:
    out = []
    for i in range(n):
        base = start + (end - start) * i / (n - 1)
        out.append(round(base + (wiggle if i % 2 else -wiggle), 4))
    return out


def flat_series(level: float = 0.5, n: int = 120, wiggle: float = 0.002) -> list[float]:
    return [round(level + (wiggle if i % 2 else -wiggle), 4) for i in range(n)]
