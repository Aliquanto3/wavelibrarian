import pytest

from wavelibrarian.core.errors import (
    BudgetExceeded,
    ConfigError,
    Inapplicable,
    NonConformantOutput,
    ProviderError,
    ValidationFailed,
    WlError,
)


def test_hierarchie() -> None:
    for classe in (
        BudgetExceeded,
        NonConformantOutput,
        ConfigError,
        Inapplicable,
        ProviderError,
        ValidationFailed,
    ):
        assert issubclass(classe, WlError)


def test_config_error() -> None:
    erreur = ConfigError("configurations[2].params.k", "entier attendu")
    assert erreur.path == "configurations[2].params.k"
    assert "entier attendu" in str(erreur)


def test_validation_failed() -> None:
    erreurs = [ConfigError("a", "x"), ConfigError("b", "y")]
    assert ValidationFailed(erreurs).errors == erreurs


def test_inapplicable_et_provider() -> None:
    assert Inapplicable("pas de store hybride").reason == "pas de store hybride"
    assert ProviderError("503", retryable=True).retryable is True
    assert ProviderError("401").retryable is False
    with pytest.raises(WlError):
        raise NonConformantOutput("json invalide")
