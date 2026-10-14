"""Un défaut d'arrêt de sonde ferme comptes et missions avant de libérer le verrou."""
from types import SimpleNamespace

from acp_poste import service_executant as module


async def test_survivant_suspend_avant_liberation_uid(tmp_path, monkeypatch):
    service = object.__new__(module.ServiceExecutant)
    service.suspendu = None
    service._pause_locale = lambda: False
    service.comptes = SimpleNamespace(echec_arret=False, occupe=False)
    service.journal = SimpleNamespace(ecrire=lambda *a, **kw: None)
    service.politique = None
    service.contexte = SimpleNamespace(
        emplacements=SimpleNamespace(verrou_codex=tmp_path / "codex.lock", verrou_claude=tmp_path / "claude.lock"),
        coffre=None, parametres_releve=lambda p: {})
    service.quotas_claude = SimpleNamespace(releve=lambda: None)
    service.execution = SimpleNamespace(mesurer_depots=lambda: None)
    liberes = []
    class VerrouObserve:
        def __init__(self, chemin): self.chemin = chemin
        def prendre(self): return self
        def rendre(self):
            assert service.suspendu == module.SUSPENDU
            assert service.comptes.echec_arret is True
            liberes.append(self.chemin)
    async def relever(*args, **kwargs):
        return None, SimpleNamespace(arret_confirme=False)
    monkeypatch.setattr(module, "Verrou", VerrouObserve)
    monkeypatch.setattr(module, "relever", relever)
    await service._sondes()
    assert len(liberes) == 2
    assert service._releves_permis() is False
