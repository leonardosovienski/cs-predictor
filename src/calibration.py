"""Calibração de probabilidades — Platt scaling (Fase 1, tentativa N+1).

Motivação (relatório da Fase 1): o Elo /400 é SOBRECONFIANTE nas pontas no
CS (previsto 0,93 → real 0,88; previsto 0,07 → real 0,19). O Platt reescala
sem tocar no rating subjacente e preserva a simetria A/B:

    q = sigmoid(a·logit(p))

a<1 achata (corrige sobreconfiança), a>1 afia. O intercepto fica em zero,
garantindo `cal(1-p) = 1-cal(p)`. Ajuste por Newton-Raphson na
log-verossimilhança (1 parâmetro, fechado em ~25
iterações) — stdlib puro, sem sklearn.

Uso prequential (backtest_calibracao.py): o calibrador só enxerga pares
(p, y) PASSADOS. Uso no serving: parâmetros materializados em
data/calibration_platt.json (ajustados no histórico completo) — model.py
aplica quando o arquivo existe.
"""
import json
import math
from pathlib import Path

_EPS = 1e-6


def _logit(p: float) -> float:
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


class PlattCalibrator:
    """q = sigmoid(a·logit(p)), simétrico e identidade até o fit."""

    def __init__(self, a: float = 1.0, b: float = 0.0):
        self.a = float(a)
        # ``b`` continua aceito para carregar artefatos legados, mas é
        # deliberadamente ignorado: intercepto não-zero quebra a invariância
        # quando team_a/team_b são trocados.
        self.b = 0.0

    def fit(self, probs: list[float], outcomes: list[int],
            iters: int = 25) -> "PlattCalibrator":
        """Newton-Raphson na NLL. outcomes: 1 = evento aconteceu."""
        if len(probs) != len(outcomes) or len(probs) < 10:
            raise ValueError("amostra insuficiente/inconsistente para o Platt")
        zs = [_logit(p) for p in probs]
        a = self.a
        for _ in range(iters):
            gradient = hessian = 0.0
            for z, y in zip(zs, outcomes):
                q = _sigmoid(a * z)
                w = max(q * (1.0 - q), 1e-9)
                gradient += (q - y) * z
                hessian += w * z * z
            if abs(hessian) < 1e-12:
                break
            da = gradient / hessian
            a -= da
            if abs(da) < 1e-9:
                break
        self.a, self.b = a, 0.0
        return self

    def apply(self, p: float) -> float:
        return _sigmoid(self.a * _logit(p))

    # ---- persistência (serving) ----
    def save(self, path: Path | str, meta: dict | None = None) -> None:
        out = {"a": round(self.a, 6), "b": round(self.b, 6), **(meta or {})}
        Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2)
                              + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "PlattCalibrator | None":
        p = Path(path)
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(a=d["a"], b=d["b"])
