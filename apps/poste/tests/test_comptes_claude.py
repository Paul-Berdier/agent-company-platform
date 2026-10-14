"""Doubles explicites de processus/auth Claude : aucun binaire, réseau, token personnel ou Docker.

La CI image mesure séparément le binaire officiel. Ici on vérifie état, corrélation, doublons, coupures et arrêt.
"""
from __future__ import annotations
import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4
import pytest
from acp_poste import comptes_claude as m
from acp_poste.comptes_codex import ControleurComptes
from acp_poste.app_server import ArretNonConfirme, MethodeRefusee, ReponseMalFormee
from acp_poste.plateforme.linux import IDENTITES
from acp_poste_contrat import comptes as C

URL = C.URL_CLAUDE + '?client_id=factice&state=ETAT-PRIVE-NE-PAS-PUBLIER&code=CODE-PRIVE'
ENV = {'HOME': '/home/acp-claude', 'CLAUDE_CONFIG_DIR': '/donnees/claude'}


def statut(**changements):
    return dict(loggedIn=False, authMethod='none', apiProvider='firstParty',
                configDirectory='/donnees/claude', email='prive@example.invalid', **changements)


class EntreeDouble:
    def __init__(self):
        self.ecritures = []
        self.fermee = False
        self.erreur = None
        self.apres = None
    def write(self, valeur):
        self.ecritures.append(valeur)
        if self.apres: self.apres()
    async def drain(self):
        if self.erreur: raise self.erreur
        await asyncio.sleep(0)
    def close(self): self.fermee = True


class ProcessusDouble:
    def __init__(self, sortie=b'', erreur=b'', code=None):
        self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
        self.stdin = EntreeDouble()
        self.stdout.feed_data(sortie)
        self.stderr.feed_data(erreur)
        self.returncode = None
        self.process = self
        self.fin = asyncio.Event()
        self.cloture_fermee = False
        if code is not None: self.terminer(code)
    def terminer(self, code=0):
        self.returncode = code
        if not self.stdout.at_eof(): self.stdout.feed_eof()
        if not self.stderr.at_eof(): self.stderr.feed_eof()
        self.fin.set()
    async def wait(self):
        await self.fin.wait()
        return self.returncode
    def close_fence(self): self.cloture_fermee = True


@pytest.fixture
def processus(monkeypatch):
    en_attente, lancements, arrets = [], [], []
    async def spawn(argv, **options):
        assert en_attente, 'Aucun vrai processus ne doit être lancé par ces tests'
        p = en_attente.pop(0)
        lancements.append((argv, options, p))
        return p
    async def arreter(p, taches, **options):
        arrets.append(options)
        p.stdin.close()
        if p.returncode is None: p.terminer(0)
        for t in taches: t.cancel()
        await asyncio.gather(*taches, return_exceptions=True)
        p.close_fence()
        return True
    monkeypatch.setattr(m, 'spawn_fenced_process', spawn)
    monkeypatch.setattr(m, '_arreter', arreter)
    return SimpleNamespace(attente=en_attente, lancements=lancements, arrets=arrets)


def document(**changements):
    obj = statut()
    obj.update(changements)
    return json.dumps(obj).encode()


@pytest.mark.parametrize('methode', ['api_key', 'api_key_helper', 'oauth_token', 'third_party'])
def test_autre_authentification_ne_confirme_pas_abonnement(methode):
    e = m.analyser_etat(document(loggedIn=True, authMethod=methode), 0, ENV['CLAUDE_CONFIG_DIR'])
    assert not e.reconnu and e.type_auth == methode and e.abonnement is None


def test_etat_filtre_identite_et_abonnement_non_rapporte():
    e = m.analyser_etat(document(loggedIn=True, authMethod='claude.ai'), 0, ENV['CLAUDE_CONFIG_DIR'])
    assert e == m.EtatClaude(True, 'claude.ai', None)
    assert 'prive' not in repr(e)
    assert m.analyser_etat(document(loggedIn=True, authMethod='claude.ai', subscriptionType='max'), 0,
                          ENV['CLAUDE_CONFIG_DIR']).abonnement == 'max'
    assert m.analyser_etat(document(loggedIn=True, authMethod='claude.ai', subscriptionType=['prive']), 0,
                          ENV['CLAUDE_CONFIG_DIR']).abonnement is None


@pytest.mark.parametrize('brut,code', [(b'{secret', 0), (b'[]', 1), (document(loggedIn='true'), 0),
    (document(authMethod=['private']), 1), (document(loggedIn=True), 0), (document(), 0),
    (document(configDirectory='/autre'), 1), (document(), 2)])
def test_etat_malforme_refuse_sans_contenu(brut, code):
    with pytest.raises(ValueError) as erreur:
        m.analyser_etat(brut, code, ENV['CLAUDE_CONFIG_DIR'])
    assert 'secret' not in str(erreur.value) and 'private' not in str(erreur.value)


@pytest.mark.parametrize('nom', ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL',
                                 'CLAUDE_CODE_USE_BEDROCK'])
async def test_provenance_environment_concurrente_refusee_avant_spawn(processus, nom):
    with pytest.raises(ValueError):
        await m.lire_etat_claude(['double'], ENV | {nom: 'secret'}, '.')
    assert processus.lancements == []


async def test_status_officiel_seul_et_sorties_privees_jetees(processus, capsys):
    p = ProcessusDouble(document(), b'PRIVE-ERREUR', 1)
    processus.attente.append(p)
    e = await m.lire_etat_claude(['double'], ENV, '.')
    assert e == m.EtatClaude(False, 'none')
    assert processus.lancements[0][0] == ['double', 'auth', 'status']
    assert p.cloture_fermee and p.stdin.fermee and processus.arrets == [{'uid': None}]
    assert 'PRIVE' not in str(capsys.readouterr())


async def test_status_timeout_et_sortie_trop_longue_sont_arretes(processus):
    p = ProcessusDouble()
    processus.attente.append(p)
    with pytest.raises(TimeoutError): await m.lire_etat_claude(['double'], ENV, '.', delai_s=.01)
    assert p.cloture_fermee
    p = ProcessusDouble(b'a' * (m.SORTIE_MAX + 1))
    processus.attente.append(p)
    with pytest.raises(ValueError): await m.lire_etat_claude(['double'], ENV, '.')
    assert p.cloture_fermee


async def test_status_arret_non_confirme_fatal_meme_pendant_erreur(processus, monkeypatch):
    async def arreter(*args, **kwargs): return False
    monkeypatch.setattr(m, '_arreter', arreter)
    processus.attente.append(ProcessusDouble(b'invalide', code=1))
    with pytest.raises(ArretNonConfirme): await m.lire_etat_claude(['double'], ENV, '.')


async def test_arret_double_limite_a_son_arbre_et_uid_uniquement_avec_setpriv(monkeypatch):
    from acp_poste.plateforme import linux
    traces = []
    async def arbre(p, grace): traces.append(('arbre', grace)); return True
    async def uid(p, identite, **kwargs): traces.append(('uid', identite)); return True
    monkeypatch.setattr(m, 'terminate_process_tree', arbre)
    monkeypatch.setattr(linux, 'arreter_agent', uid)
    p = ProcessusDouble(code=0)
    assert await m._arreter(p, [], uid=m._uid_claude(['double']))
    assert await m._arreter(p, [], uid=m._uid_claude(['/usr/bin/setpriv', '--reuid=10002', '--regid=10002', '--', 'double']))
    assert traces == [('arbre', .2), ('uid', 10002)]
    assert m._uid_claude(['/usr/bin/setpriv', '--', 'double', '--reuid=10002', '--regid=10002']) is None


async def test_login_fragmente_code_opaque_env_et_retransmission_sans_double_ecriture(processus, capsys):
    p = ProcessusDouble()
    processus.attente.append(p)
    async with m.SessionCompteClaude(['double'], env=ENV, cwd='.') as s:
        p.stdout.feed_data(URL[:40].encode())
        await asyncio.sleep(0)
        assert not s.defi.done()
        p.stdout.feed_data((URL[40:] + '\nPaste code here if prompted: ').encode())
        assert await asyncio.wait_for(s.defi, 1) == URL
        identifiant = str(uuid4())
        assert await s.fournir_code(identifiant, 'CODE-OPAQUE#état')
        assert await s.fournir_code(identifiant, 'CODE-OPAQUE#état')
        assert p.stdin.ecritures == ['CODE-OPAQUE#état\n'.encode()]
        with pytest.raises(MethodeRefusee): await s.fournir_code(identifiant, 'autre')
        with pytest.raises(MethodeRefusee): await s.fournir_code(str(uuid4()), 'CODE-OPAQUE#état')
    assert s.arret_confirme is True and p.cloture_fermee
    assert processus.lancements[0][0] == ['double', 'auth', 'login', '--claudeai']
    assert 'CODE-OPAQUE' not in str(capsys.readouterr()) and 'ETAT-PRIVE' not in str(capsys.readouterr())


async def test_code_invalide_et_echec_drain_ne_sont_jamais_rejoues(processus):
    p = ProcessusDouble((URL + '\nPaste code here if prompted: ').encode())
    processus.attente.append(p)
    async with m.SessionCompteClaude(['double'], env=ENV, cwd='.') as s:
        await s.defi
        for code in ('a\nb', '\x00', 'x' * 2049):
            with pytest.raises(MethodeRefusee): await s.fournir_code(str(uuid4()), code)
        identifiant = str(uuid4())
        p.stdin.erreur = BrokenPipeError('PRIVE')
        with pytest.raises(ReponseMalFormee): await s.fournir_code(identifiant, 'opaque')
        assert await s.fournir_code(identifiant, 'opaque') is False
        assert p.stdin.ecritures == [b'opaque\n']


@pytest.mark.parametrize('sortie', [b'https://evil.invalid/auth\nPaste code here if prompted: ',
                                   b'No challenge', b'x' * (m.SORTIE_MAX + 1)],
                         ids=['hote_refuse', 'defi_absent', 'sortie_trop_longue'])
async def test_dialogue_incompatible_ferme_le_processus(processus, sortie):
    p = ProcessusDouble(sortie, code=1)
    processus.attente.append(p)
    with pytest.raises(ReponseMalFormee):
        async with m.SessionCompteClaude(['double'], env=ENV, cwd='.') as s:
            await s.defi
    assert p.cloture_fermee and s.arret_confirme is True


async def attendre(predicate):
    async def boucle():
        while not predicate(): await asyncio.sleep(0)
    await asyncio.wait_for(boucle(), 1)


@pytest.fixture
def ctl(tmp_path, processus):
    contexte = SimpleNamespace(plateforme='linux',
        emplacements=SimpleNamespace(verrou_codex=tmp_path/'codex.lock', verrou_claude=tmp_path/'claude.lock'),
        identites={'claude': IDENTITES['acp-claude']}, lanceurs_pour=lambda p: {'claude': ['double']})
    politique = SimpleNamespace(claude=SimpleNamespace(config_dir=tmp_path, version_testee=m.VERSION_CLAUDE), codex=None)
    class ProtocoleDouble:
        def __init__(self): self.reponses=[]; self.appels=[]
        def comptes(self, jeton, corps):
            self.appels.append(corps)
            if not self.reponses: return {'protocole': C.PROTOCOLE, 'operation': None}
            reponse = self.reponses.pop(0)
            if isinstance(reponse, Exception): raise reponse
            return reponse
    async def version(*args): return m.VERSION_CLAUDE
    lectures=[]
    async def etat(*args):
        lectures.append(args)
        return m.EtatClaude(c.compte_reconnu, 'claude.ai' if c.compte_reconnu else 'none')
    c = ControleurComptes(contexte, politique, ProtocoleDouble(), None, libre=lambda: True,
                         apres=lambda: None, version=version, etat_claude=etat)
    c.compte_reconnu=False
    c.lectures=lectures
    return c


def cmd(identifiant=None, action='demarrer', retour=None, delai=60):
    return {'protocole': C.PROTOCOLE, 'operation': {'id': identifiant or str(uuid4()), 'moteur': 'claude_code',
        'action': action, 'limite_attente_le': int(time.time()) + delai, 'retour_code': retour}}


async def demarrer(ctl, processus):
    p = ProcessusDouble((URL + '\nPaste code here if prompted: ').encode())
    processus.attente.append(p)
    rep = cmd()
    ctl.protocole.reponses.append(rep)
    await ctl.tour()
    await attendre(lambda: ctl.observation['etat'] == 'code_disponible')
    return p, rep['operation']['id']


async def test_controleur_code_ack_perdu_et_double_envoi_sans_nouveau_login(ctl, processus):
    p, op = await demarrer(ctl, processus)
    retour = {'defi_id': ctl.defi_id, 'soumission_id': str(uuid4()), 'code': 'opaque'}
    ctl.protocole.reponses.append(cmd(op, 'fournir_code', retour))
    await ctl.tour()
    assert ctl.observation['etat'] == 'verification'
    assert ctl.observation['code_transmis'] == {k: v for k, v in retour.items() if k != 'code'}
    ctl.protocole.reponses.append(OSError('réponse perdue simulée'))
    with pytest.raises(OSError): await ctl.tour()
    ctl.protocole.reponses.append(cmd(op, 'fournir_code', retour))
    await ctl.tour()
    assert p.stdin.ecritures == [b'opaque\n'] and len(processus.lancements) == 1
    ctl.compte_reconnu=True
    p.terminer(0)
    await ctl.tache
    assert ctl.observation['etat'] == 'connecte' and ctl.observation['code_transmis']['soumission_id'] == retour['soumission_id']
    assert ctl.observation['verification_url'] is None and ctl.observation['code_utilisateur'] is None


@pytest.mark.parametrize('reconnu', [False, True])
async def test_annulation_code_sortie_zero_ne_devient_pas_connexion(ctl, processus, reconnu):
    p, op = await demarrer(ctl, processus)
    ctl.compte_reconnu=reconnu
    ctl.protocole.reponses.append(cmd(op, 'annuler'))
    await ctl.tour()
    await ctl.tache
    assert p.returncode == 0
    assert ctl.observation['etat'] == 'annulee' and ctl.observation['compte_connecte'] is reconnu
    assert p.stdin.ecritures == [] and len(ctl.lectures) == 1


async def test_sortie_zero_sans_code_ne_prouve_pas_reconnexion(ctl, processus):
    p, op = await demarrer(ctl, processus)
    ctl.compte_reconnu=True
    p.terminer(0)
    await ctl.tache
    assert ctl.observation['etat'] == 'erreur' and ctl.observation['compte_connecte'] is True


@pytest.mark.parametrize('action', ['reconcilier', 'attendre', 'annuler'])
async def test_reprise_relit_et_ne_relance_jamais_login(ctl, processus, action):
    ctl.compte_reconnu=True
    ctl.protocole.reponses.append(cmd(action=action))
    await ctl.tour()
    await ctl.tache
    assert processus.lancements == [] and len(ctl.lectures) == 1
    assert ctl.observation['etat'] == ('annulee' if action == 'annuler' else 'interrompue')


async def test_code_etranger_et_ancienne_operation_ne_sont_pas_transmis(ctl, processus):
    p, op = await demarrer(ctl, processus)
    for identifiant, defi in ((str(uuid4()), ctl.defi_id), (op, str(uuid4()))):
        ctl.protocole.reponses.append(cmd(identifiant, 'fournir_code',
            {'defi_id': defi, 'soumission_id': str(uuid4()), 'code': 'opaque'}))
        await ctl.tour()
    assert not p.stdin.ecritures
    ctl.annulation.set()
    await ctl.tache


async def test_code_orphelin_apres_redemarrage_ne_lance_rien(ctl, processus):
    ctl.protocole.reponses.append(cmd(action='fournir_code',
        retour={'defi_id': str(uuid4()), 'soumission_id': str(uuid4()), 'code': 'opaque'}))
    await ctl.tour()
    assert ctl.tache is None and processus.lancements == []


async def test_login_arret_non_confirme_suspend_toutes_les_voies(ctl, processus, monkeypatch):
    p, op = await demarrer(ctl, processus)
    arret_original = m._arreter
    async def mauvais(*args, **kwargs):
        await arret_original(*args, **kwargs)
        return False
    monkeypatch.setattr(m, '_arreter', mauvais)
    suspensions=[]
    ctl.suspendre=lambda: suspensions.append(True)
    ctl.annulation.set()
    await ctl.tache
    assert ctl.echec_arret and ctl.occupe and suspensions == [True]
    assert ctl.observation['etat'] == 'erreur' and ctl.lectures == []


@pytest.mark.parametrize('action', ['reconcilier', 'demarrer'])
async def test_annulation_pendant_status_reste_prioritaire(ctl, processus, action):
    entree, fin = asyncio.Event(), asyncio.Event()
    async def etat(*args):
        entree.set()
        await fin.wait()
        return m.EtatClaude(True, 'claude.ai')
    ctl.etat_claude = etat
    if action == 'demarrer':
        p, op = await demarrer(ctl, processus)
        retour = {'defi_id': ctl.defi_id, 'soumission_id': str(uuid4()), 'code': 'opaque'}
        ctl.protocole.reponses.append(cmd(op, 'fournir_code', retour))
        await ctl.tour()
        p.terminer(0)
    else:
        rep = cmd(action=action)
        op = rep['operation']['id']
        ctl.protocole.reponses.append(rep)
        await ctl.tour()
    await asyncio.wait_for(entree.wait(), 1)
    ctl.protocole.reponses.append(cmd(op, 'annuler'))
    await ctl.tour()
    fin.set()
    await ctl.tache
    assert ctl.observation['etat'] == 'annulee' and ctl.observation['compte_connecte'] is True


@pytest.mark.parametrize('confirme', [False, True])
async def test_arret_attend_la_preuve_meme_avec_deux_annulations(monkeypatch, confirme):
    entree, fin = asyncio.Event(), asyncio.Event()
    async def arreter(*args, **kwargs):
        entree.set()
        await fin.wait()
        return confirme
    monkeypatch.setattr(m, '_arreter', arreter)
    tache = asyncio.create_task(m._fermer(None, []))
    await entree.wait()
    tache.cancel()
    await asyncio.sleep(0)
    tache.cancel()
    await asyncio.sleep(0)
    assert not tache.done()
    fin.set()
    with pytest.raises(asyncio.CancelledError if confirme else ArretNonConfirme):
        await tache


async def test_sortie_cli_avant_fin_drain_attend_transmission_confirmee(ctl, processus):
    p, op = await demarrer(ctl, processus)
    entree, fin = asyncio.Event(), asyncio.Event()
    async def drain():
        entree.set()
        await fin.wait()
    p.stdin.drain = drain
    p.stdin.apres = lambda: p.terminer(0)
    ctl.compte_reconnu = True
    retour = {'defi_id': ctl.defi_id, 'soumission_id': str(uuid4()), 'code': 'opaque'}
    ctl.protocole.reponses.append(cmd(op, 'fournir_code', retour))
    envoi = asyncio.create_task(ctl.tour())
    await entree.wait()
    await asyncio.sleep(0)
    assert ctl.occupe and ctl.observation['etat'] == 'code_disponible'
    fin.set()
    await envoi
    await ctl.tache
    assert p.stdin.ecritures == [b'opaque\n']
    assert ctl.observation['etat'] == 'connecte' and ctl.observation['code_transmis']['soumission_id'] == retour['soumission_id']
