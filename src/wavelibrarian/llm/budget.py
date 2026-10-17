"""Registre de dépense `ledger.sqlite` (AD-9) : réserver, puis régler ou libérer.

Le registre est l'unique source du Plafond. Montants en `Decimal`, stockés en chaîne, dans la
devise du fournisseur. Le plafond par Exécution somme les réservations ouvertes et les montants
réglés de l'Exécution ; le plafond de période somme celles du mois civil UTC, toutes Exécutions
confondues. Un fournisseur sans plafond n'est pas limité.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from wavelibrarian.config.experiment import Amount, Budget
from wavelibrarian.core.errors import BudgetExceeded, ConfigError, WlError
from wavelibrarian.llm._db import connect, resolve_wl_home, transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    currency TEXT NOT NULL,
    period TEXT NOT NULL,
    estimated TEXT NOT NULL,
    actual TEXT,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'released'))
)
"""
# Montant compté : estimé si encore réservé, réel si réglé, rien si libéré.
_COMPTE = {"reserved": "estimated", "settled": "actual"}


@dataclass(frozen=True)
class Balance:
    """Solde d'un fournisseur ; `None` = pas de plafond de ce type."""

    currency: str | None
    run_remaining: Decimal | None
    period_remaining: Decimal | None

    @property
    def remaining(self) -> Decimal | None:
        """Le plus petit des deux soldes ; `None` si le fournisseur n'a aucun plafond."""
        valeurs = [v for v in (self.run_remaining, self.period_remaining) if v is not None]
        return min(valeurs) if valeurs else None


def _maintenant() -> datetime:
    return datetime.now(UTC)


class Ledger:
    """Registre de dépense persistant, sûr entre processus (`BEGIN IMMEDIATE`)."""

    def __init__(
        self,
        budget: Budget,
        run_id: str,
        wl_home: Path | None = None,
        clock: Callable[[], datetime] = _maintenant,
        *,
        recover_orphans: bool = False,
    ) -> None:
        """`recover_orphans=True` seulement par le runner, après avoir pris `run.lock` (AD-11).

        Sinon, un second `Ledger` ouvert pendant une Exécution réglerait ses réservations en
        cours, et le `settle` qui suit perdrait le coût réel. Une réservation laissée ouverte
        compte déjà au montant estimé : ne pas la récupérer ne fait jamais dépasser un plafond.
        """
        self._budget = budget
        self._run_id = run_id
        self._clock = clock
        self._conn = connect(resolve_wl_home(wl_home) / "ledger.sqlite")
        try:
            self._conn.execute(_SCHEMA)
            if recover_orphans:
                self.recover_orphans()
        except BaseException:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _periode(self) -> str:
        maintenant = self._clock()
        if maintenant.tzinfo is None:
            raise ValueError("horloge naïve : le mois civil se calcule en UTC")
        return f"{maintenant.astimezone(UTC):%Y-%m}"

    def recover_orphans(self) -> int:
        """Règle au montant estimé toute réservation laissée ouverte (arrêt brutal, AD-11).

        Valable seulement si l'appelant tient `run.lock` (une seule Exécution à la fois).
        """
        with transaction(self._conn) as c:
            return c.execute(
                "UPDATE reservations SET status='settled', actual=estimated WHERE status='reserved'"
            ).rowcount

    def _plafonds(self, provider: str) -> tuple[Amount | None, Amount | None]:
        return self._budget.per_run.get(provider), self._budget.period.get(provider)

    @staticmethod
    def _somme(c: sqlite3.Connection, where: str, args: tuple[str, ...]) -> Decimal:
        total = Decimal(0)
        for statut, colonne in _COMPTE.items():
            rows = c.execute(
                f"SELECT {colonne} FROM reservations WHERE status=? AND {where}",  # noqa: S608
                (statut, *args),
            )
            total += sum((Decimal(r[0]) for r in rows), Decimal(0))
        return total

    def _depenses(
        self, c: sqlite3.Connection, provider: str, currency: str, periode: str
    ) -> tuple[Decimal, Decimal]:
        autre = c.execute(
            "SELECT currency FROM reservations WHERE provider=? AND currency<>? "
            "AND status<>'released' AND (run_id=? OR period=?) LIMIT 1",
            (provider, currency, self._run_id, periode),
        ).fetchone()
        if autre is not None:
            raise ConfigError(
                f"budget.{provider}",
                f"dépenses déjà comptées en {autre[0]}, plafond en {currency} : "
                "changer de devise en cours de mois mélangerait les montants",
            )
        cle = "provider=? AND currency=?"
        run = self._somme(c, f"{cle} AND run_id=?", (provider, currency, self._run_id))
        per = self._somme(c, f"{cle} AND period=?", (provider, currency, periode))
        return run, per

    def reserve(self, provider: str, amount: Decimal, currency: str) -> int:
        """Réserve `amount` ; `BudgetExceeded` si un plafond serait dépassé. Renvoie l'id."""
        if amount < 0:
            raise ValueError(f"montant de réservation négatif : {amount}")
        per_run, period = self._plafonds(provider)
        for cap in (per_run, period):
            if cap is not None and cap.currency != currency:
                raise ConfigError(
                    f"budget.{provider}",
                    f"réservation en {currency} mais plafond en {cap.currency}",
                )
        periode = self._periode()
        with transaction(self._conn) as c:
            if per_run is None and period is None:
                run = per = Decimal(0)  # sans plafond : ni limite ni contrôle de devise
            else:
                run, per = self._depenses(c, provider, currency, periode)
            if per_run is not None and run + amount > per_run.amount:
                raise BudgetExceeded(
                    f"{provider} : plafond par Exécution de {per_run.amount} {currency} dépassé "
                    f"({run} + {amount})"
                )
            if period is not None and per + amount > period.amount:
                raise BudgetExceeded(
                    f"{provider} : plafond de période de {period.amount} {currency} dépassé "
                    f"({per} + {amount}, mois {periode})"
                )
            cur = c.execute(
                "INSERT INTO reservations (run_id, provider, currency, period, estimated, status) "
                "VALUES (?, ?, ?, ?, ?, 'reserved')",
                (self._run_id, provider, currency, periode, str(amount)),
            )
            return int(cur.lastrowid or 0)

    def _clore(self, reservation: int, statut: str, actual: Decimal | None) -> None:
        with transaction(self._conn) as c:
            n = c.execute(
                "UPDATE reservations SET status=?, actual=? WHERE id=? AND status='reserved'",
                (statut, None if actual is None else str(actual), reservation),
            ).rowcount
            if n != 1:
                raise WlError(f"réservation {reservation} inconnue ou déjà close")

    def settle(self, reservation: int, actual: Decimal) -> None:
        """Règle la réservation au coût réel (peut dépasser l'estimation : l'appel est payé)."""
        if actual < 0:
            raise ValueError(f"coût réel négatif : {actual}")
        self._clore(reservation, "settled", actual)

    def release(self, reservation: int) -> None:
        """Libère la réservation (appel en erreur) : elle ne compte plus."""
        self._clore(reservation, "released", None)

    def balance(self, provider: str) -> Balance:
        """Soldes restants du fournisseur, dans la devise de son plafond."""
        per_run, period = self._plafonds(provider)
        cap = per_run or period
        if cap is None:
            return Balance(currency=None, run_remaining=None, period_remaining=None)
        run, per = self._depenses(self._conn, provider, cap.currency, self._periode())
        return Balance(
            currency=cap.currency,
            run_remaining=None if per_run is None else per_run.amount - run,
            period_remaining=None if period is None else period.amount - per,
        )
