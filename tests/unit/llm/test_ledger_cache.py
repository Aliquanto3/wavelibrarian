"""Story 1.8 : registre de dépense et Cache de réponses LLM (sans réseau)."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from wavelibrarian.config.experiment import Amount, Budget
from wavelibrarian.core.errors import BudgetExceeded, ConfigError, WlError
from wavelibrarian.core.types import Usage
from wavelibrarian.llm.budget import Ledger
from wavelibrarian.llm.cache import ResponseCache, cache_key
from wavelibrarian.ports.gateway import LLMRequest, Message

D = Decimal


def usd(x: str) -> Amount:
    return Amount(amount=D(x), currency="USD")


def budget(run: str = "1.00", period: str = "2.00") -> Budget:
    return Budget(per_run={"anthropic": usd(run)}, period={"anthropic": usd(period)})


def horloge(etat: dict[str, datetime]):  # type: ignore[no-untyped-def]
    return lambda: etat["now"]


def test_reserver_regler_puis_refus(wl_home: Path) -> None:
    with Ledger(budget(), "r1", wl_home) as lg:
        trace: list[str] = []
        lg._conn.set_trace_callback(trace.append)
        r = lg.reserve("anthropic", D("0.60"), "USD")
        lg.settle(r, D("0.40"))
        with pytest.raises(BudgetExceeded):
            lg.reserve("anthropic", D("0.70"), "USD")
        assert lg.balance("anthropic").remaining == D("0.60")
        assert lg.balance("anthropic").run_remaining == D("0.60")
        # Chaque écriture ouvre une transaction BEGIN IMMEDIATE.
        assert trace.count("BEGIN IMMEDIATE") == 3  # reserve, settle, reserve refusée
        assert trace.count("COMMIT") == 2 and trace.count("ROLLBACK") == 1
        assert all(
            s.startswith(("INSERT", "UPDATE")) is False or i > 0 and trace[i - 1] != "COMMIT"
            for i, s in enumerate(trace)
        )


def test_ecriture_toujours_dans_begin_immediate(wl_home: Path) -> None:
    with Ledger(budget(), "r1", wl_home) as lg:
        trace: list[str] = []
        lg._conn.set_trace_callback(trace.append)
        lg.release(lg.reserve("anthropic", D("0.10"), "USD"))
    ecritures = [i for i, s in enumerate(trace) if s.startswith(("INSERT", "UPDATE"))]
    assert len(ecritures) == 2
    for i in ecritures:
        debut = max(j for j in range(i) if trace[j] in ("BEGIN IMMEDIATE", "COMMIT"))
        assert trace[debut] == "BEGIN IMMEDIATE"


def test_plafond_de_periode_et_mois_suivant(wl_home: Path) -> None:
    etat = {"now": datetime(2026, 10, 31, 23, 59, tzinfo=UTC)}
    b = Budget(per_run={"anthropic": usd("5.00")}, period={"anthropic": usd("3.00")})
    for run in ("a", "b"):
        with Ledger(b, run, wl_home, clock=horloge(etat)) as lg:
            lg.settle(lg.reserve("anthropic", D("1.50"), "USD"), D("1.50"))
    with Ledger(b, "c", wl_home, clock=horloge(etat)) as lg:
        with pytest.raises(BudgetExceeded, match="période"):
            lg.reserve("anthropic", D("0.10"), "USD")
        etat["now"] = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        lg.reserve("anthropic", D("0.10"), "USD")
        assert lg.balance("anthropic").period_remaining == D("2.90")


def test_reservation_orpheline_reglee_a_l_estimation(wl_home: Path) -> None:
    lg = Ledger(budget(), "r1", wl_home)
    lg.reserve("anthropic", D("0.30"), "USD")
    lg.close()  # arrêt brutal : jamais réglée
    with Ledger(budget(), "r1", wl_home) as lg2:
        assert lg2.balance("anthropic").run_remaining == D("0.70")
        lg2.recover_orphans()  # idempotent
        assert lg2.balance("anthropic").run_remaining == D("0.70")


def test_reservation_liberee_ne_compte_plus(wl_home: Path) -> None:
    with Ledger(budget(), "r1", wl_home) as lg:
        r = lg.reserve("anthropic", D("0.90"), "USD")
        assert lg.balance("anthropic").run_remaining == D("0.10")
        lg.release(r)
        assert lg.balance("anthropic").run_remaining == D("1.00")
        with pytest.raises(WlError):
            lg.settle(r, D("0.10"))  # déjà close
        lg.reserve("anthropic", D("0.90"), "USD")


def test_devises_et_plafonds_par_fournisseur(wl_home: Path) -> None:
    b = Budget(
        per_run={"anthropic": usd("1.00"), "azure": Amount(amount=D("0.50"), currency="EUR")},
        period={},
    )
    with Ledger(b, "r1", wl_home) as lg:
        lg.reserve("anthropic", D("1.00"), "USD")  # n'entame pas le plafond azure
        lg.reserve("azure", D("0.50"), "EUR")
        with pytest.raises(BudgetExceeded):
            lg.reserve("azure", D("0.01"), "EUR")
        with pytest.raises(ConfigError, match="EUR"):
            lg.reserve("anthropic", D("0.01"), "EUR")
        assert lg.balance("azure").currency == "EUR"
        assert lg.balance("ollama").remaining is None  # sans plafond : illimité
        lg.reserve("ollama", D("0"), "EUR")


def test_plafond_par_execution_isole_les_executions(wl_home: Path) -> None:
    b = Budget(per_run={"anthropic": usd("1.00")}, period={})
    with Ledger(b, "a", wl_home) as lg:
        lg.settle(lg.reserve("anthropic", D("1.00"), "USD"), D("1.00"))
    with Ledger(b, "b", wl_home) as lg:
        lg.reserve("anthropic", D("1.00"), "USD")


def test_montants_negatifs_refuses(wl_home: Path) -> None:
    with Ledger(budget(), "r1", wl_home) as lg:
        with pytest.raises(ValueError):
            lg.reserve("anthropic", D("-1"), "USD")
        with pytest.raises(ValueError):
            lg.settle(lg.reserve("anthropic", D("1"), "USD"), D("-1"))


def test_wl_home_par_variable_d_environnement(wl_home: Path) -> None:
    with Ledger(budget(), "r1"):
        pass
    ResponseCache().close()
    assert (wl_home / "ledger.sqlite").exists() and (wl_home / "llm_cache.sqlite").exists()


def test_concurrence_threads_jamais_au_dela_du_plafond(wl_home: Path) -> None:
    b = Budget(per_run={"anthropic": usd("1.00")}, period={})
    Ledger(b, "r1", wl_home).close()  # crée le schéma

    def travailleur(_: int) -> int:
        with Ledger(b, "r1", wl_home, recover_orphans=False) as lg:
            ok = 0
            for _i in range(5):
                try:
                    lg.reserve("anthropic", D("0.10"), "USD")
                    ok += 1
                except BudgetExceeded:
                    pass
            return ok

    with ThreadPoolExecutor(max_workers=4) as pool:
        acceptees = sum(pool.map(travailleur, range(4)))
    assert acceptees == 10
    with Ledger(b, "r1", wl_home, recover_orphans=False) as lg:
        assert lg.balance("anthropic").run_remaining == D("0.00")


_SCRIPT = """
import sys
from decimal import Decimal
from pathlib import Path
from wavelibrarian.config.experiment import Amount, Budget
from wavelibrarian.core.errors import BudgetExceeded
from wavelibrarian.llm.budget import Ledger
b = Budget(per_run={"anthropic": Amount(amount=Decimal("1.00"), currency="USD")}, period={})
ok = 0
with Ledger(b, "r1", Path(sys.argv[1]), recover_orphans=False) as lg:
    for _ in range(8):
        try:
            lg.reserve("anthropic", Decimal("0.10"), "USD")
            ok += 1
        except BudgetExceeded:
            pass
print(ok)
"""


def test_concurrence_deux_processus(wl_home: Path) -> None:
    Ledger(budget(), "r1", wl_home).close()
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _SCRIPT, str(wl_home)],
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    total = sum(int(p.communicate(timeout=60)[0]) for p in procs)
    assert total == 10


# --- Cache de réponses ---


def req(**kw: object) -> LLMRequest:
    base: dict[str, object] = {
        "model_id": "m",
        "role": "closed_book",
        "step": "generate",
        "system": "sys",
        "messages": (Message(role="user", content="q"),),
        "max_tokens": 100,
    }
    return LLMRequest(**{**base, **kw})  # type: ignore[arg-type]


def test_cache_relit_texte_et_usage(wl_home: Path) -> None:
    usage = Usage(input_tokens=12, output_tokens=3, cache_read_tokens=5, cache_write_tokens=1)
    cache = ResponseCache(wl_home)
    cle = cache_key(req(), "anthropic")
    assert cache.get(cle) is None
    cache.put(cle, "réponse é", usage)
    cache.put(cle, "autre", Usage())  # première réponse gardée
    cache.close()
    rel = ResponseCache(wl_home).get(cle)  # persistant
    assert rel is not None and rel.text == "réponse é" and rel.usage == usage


def test_cle_sensible_a_pass_id_message_temperature_pas_a_step() -> None:
    ref = cache_key(req(), "anthropic")
    assert cache_key(req(pass_id=1), "anthropic") != ref
    assert cache_key(req(messages=(Message(role="user", content="q2"),)), "anthropic") != ref
    assert cache_key(req(temperature=0.7), "anthropic") != ref
    assert cache_key(req(system="autre"), "anthropic") != ref
    assert cache_key(req(model_id="n"), "anthropic") != ref
    assert cache_key(req(step="rerank"), "anthropic") == ref
    assert cache_key(req(cache_system=True, timeout_s=3.0), "anthropic") == ref


def test_inputs_dans_la_cle_seulement_pour_le_provider_fake() -> None:
    a, b = req(inputs={"k": 1}), req(inputs={"k": 2})
    assert cache_key(a, "anthropic") == cache_key(b, "anthropic")
    assert cache_key(a, "ollama") == cache_key(b, "ollama")
    assert cache_key(a, "fake") != cache_key(b, "fake")
