// Réponses RÉELLES des routes du propriétaire de l'étape P6 (greffon acp-poste), capturées le 01/10/2026 dans
// l'image de test construite depuis l'arbre de refonte/hermes-p6 (routeur du greffon, couture par jeton de Hermes,
// session factice, HERMES_HOME jetable) : exécutant Railway enrôlé avec l'inventaire Linux de l'exemple partagé
// (hermes/tests/outils/fixtures_machine/inventaire_requete_linux.json, régime B), sans carte, avec une carte en
// main (battement puis réclamation), routage après la première carte terminée (résolution observée), carte en
// revue pour des fichiers de pilotage (GET /v1/questions), revue acceptée, puis branche intégrée prête. Rien n'est
// modifié à la main.
export const FORMES_EXECUTANT = {
  "poste_executant_sans_carte": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": null,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "etat": "hors_ligne",
      "machine": "m3b7783ebfe4",
      "message": "Poste confirmé mais jamais vu depuis : démarrez son service (tâche planifiée).",
      "derniere_vue": null,
      "hors_ligne_depuis": null
    },
    "machine": {
      "machine": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": null,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "machines": {
        "a_confirmer": 0,
        "actif": 1,
        "revoque": 0
      },
      "codes_utilisables": 0
    },
    "inventaire": {
      "id": 1,
      "machine_id": "m3b7783ebfe4",
      "recu_le": 1790853175,
      "releve_le": 1790853175,
      "contenu": {
        "alertes": [
          "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
        ],
        "bac_a_sable_codex": null,
        "connexions": {
          "claude": "jeton_reconnu",
          "codex": "compte_chatgpt",
          "plan_codex": "prolite"
        },
        "depots": [
          {
            "alias": "jetable"
          }
        ],
        "isolement_linux": {
          "bwrap": "refuse",
          "codex_sans_bac_a_sable": "refuse",
          "ecriture_admise": {
            "claude": true,
            "codex": false
          },
          "proc_neuf": false,
          "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
          "regime": "B",
          "reseau_coupe": false,
          "sonde_le": "2026-10-01T11:12:55Z",
          "uid_separes": true
        },
        "politique": {
          "alias_claude_permis": [
            "opus",
            "sonnet"
          ],
          "cartes_par_jour": 20,
          "concurrence": 1,
          "conditions": {
            "claude": "2026-10-01",
            "codex": "2026-10-01"
          },
          "duree_max_carte_s": 3600,
          "efforts_interdits": [
            "max",
            "ultra",
            "ultracode"
          ],
          "executants": [
            "codex",
            "claude"
          ],
          "modeles_codex_permis": [],
          "paliers_admis": [
            "default"
          ],
          "reseau_executants": false
        },
        "poste": {
          "compte": "uid_dedie",
          "hermes_meme_enveloppe_que_codex": true,
          "hote": "railway",
          "nom": "Exécutant Railway",
          "noyau": "6.12.10",
          "plateforme": "linux",
          "politique_empreinte": "5d1e0c7a9b42",
          "python": "3.12.10",
          "windows": null
        },
        "protocole": "acp-machine/1",
        "releve_le": "2026-10-01T11:12:55Z",
        "releves": {
          "poste-claude": 2,
          "poste-codex": 1
        },
        "version_poste": "1.0.0",
        "versions": {
          "claude": {
            "conforme": true,
            "lue": "2.1.283",
            "testee": "2.1.283"
          },
          "codex": {
            "conforme": true,
            "lue": "0.156.1",
            "testee": "0.156.1"
          }
        }
      },
      "alertes": [
        "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      ]
    },
    "alertes": [
      "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
    ],
    "ordres": [],
    "catalogue": {
      "etat": "connu",
      "voies": {
        "poste-codex": {
          "etat": "a_jour",
          "releve_id": 1,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 0,
          "perime": false,
          "source": "poste",
          "version_cli": "0.156.1",
          "modeles": [
            {
              "id": "factice-codex-1",
              "displayName": "Factice 1",
              "isDefault": true,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [
                "default",
                "priority"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-1",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            },
            {
              "id": "factice-codex-2",
              "displayName": "Factice 2",
              "isDefault": false,
              "supportedReasoningEfforts": [
                "low",
                "medium"
              ],
              "defaultReasoningEffort": "low",
              "serviceTiers": [
                "default"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-2",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            }
          ],
          "quotas": {
            "pourcentage_utilise": 41.0,
            "remise_a_zero": "2026-09-26T12:00:00Z"
          },
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "compte",
          "detail": null,
          "documentation_lue_le": null,
          "compteurs": [
            {
              "provider": "codex",
              "status": "ok",
              "source": "codex_app_server",
              "plan": "prolite",
              "limit_id": "codex",
              "windows": [
                {
                  "key": "primary",
                  "used_percent": 41,
                  "window_minutes": 300,
                  "resets_at": "2026-09-26T12:00:00Z"
                },
                {
                  "key": "secondary",
                  "used_percent": 12,
                  "window_minutes": 10080,
                  "resets_at": "2026-09-30T08:00:00Z"
                }
              ],
              "credits": null,
              "limit_reached": false,
              "reached_type": null,
              "observed_at": "2026-10-01T11:12:55Z",
              "detail": null
            }
          ],
          "badge": "releve_du_compte",
          "badge_libelle": "Relevé du compte"
        },
        "poste-claude": {
          "etat": "a_jour",
          "releve_id": 2,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 0,
          "perime": false,
          "source": "poste",
          "version_cli": "2.1.283",
          "modeles": [
            {
              "id": "opus",
              "displayName": "opus",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "opus[1m]",
              "displayName": "opus[1m]",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "haiku",
              "displayName": "haiku",
              "isDefault": null,
              "supportedReasoningEfforts": [],
              "defaultReasoningEffort": null,
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": null,
              "source_efforts": "documentation"
            }
          ],
          "quotas": null,
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "alias_documentes",
          "detail": null,
          "documentation_lue_le": "2026-09-26",
          "compteurs": [],
          "badge": "alias_documentes",
          "badge_libelle": "Alias documentés"
        }
      },
      "hermes": {
        "modele": "modèle par défaut du profil"
      },
      "routage": {
        "valide": false,
        "classes": {}
      },
      "politique": {
        "efforts_interdits": [
          "max",
          "ultra",
          "ultracode"
        ],
        "paliers_admis": [
          "default"
        ],
        "voies_par_classe": {
          "exploration": [
            "poste-claude",
            "poste-codex"
          ],
          "planification": [
            "hermes"
          ],
          "synthese": [
            "hermes"
          ],
          "repondre": [
            "hermes"
          ],
          "recherche_web": [
            "hermes"
          ],
          "architecture": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "implementation": [
            "poste-codex",
            "poste-claude"
          ],
          "debogage_tests": [
            "poste-codex",
            "poste-claude"
          ],
          "petite_tache": [
            "poste-codex",
            "poste-claude"
          ],
          "documentation": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "relecture": [
            "poste-codex",
            "poste-claude"
          ],
          "integration": [
            "poste-integration"
          ]
        }
      },
      "releve_factice": false
    },
    "executant": {
      "connu": true,
      "plateforme": "linux",
      "hote": "railway",
      "noyau": "6.12.10",
      "isolement": {
        "bwrap": "refuse",
        "codex_sans_bac_a_sable": "refuse",
        "ecriture_admise": {
          "claude": true,
          "codex": false
        },
        "proc_neuf": false,
        "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
        "regime": "B",
        "reseau_coupe": false,
        "sonde_le": "2026-10-01T11:12:55Z",
        "uid_separes": true
      },
      "bac_a_sable_codex": null,
      "conditions": {
        "claude": "2026-10-01",
        "codex": "2026-10-01"
      },
      "bornes": {
        "cartes_par_jour": 20,
        "duree_max_carte_s": 3600,
        "concurrence": 1
      },
      "peut_executer": null,
      "voies_disponibles": null,
      "espace_libre_mio": null,
      "voies_fermees": {
        "poste-codex": "isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      },
      "cartes_en_attente_de_voie": [],
      "carte_en_cours": null,
      "branches_pretes": [],
      "revues": 0
    }
  },
  "poste_executant_carte": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790853176,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "machine": "m3b7783ebfe4",
      "message": null,
      "etat": "en_ligne",
      "derniere_vue": 1790853176,
      "derniere_vue_lisible": "01/10/2026 13:12",
      "hors_ligne_depuis": null,
      "source": "longpoll"
    },
    "machine": {
      "machine": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790853176,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "machines": {
        "a_confirmer": 0,
        "actif": 1,
        "revoque": 0
      },
      "codes_utilisables": 0
    },
    "inventaire": {
      "id": 1,
      "machine_id": "m3b7783ebfe4",
      "recu_le": 1790853175,
      "releve_le": 1790853175,
      "contenu": {
        "alertes": [
          "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
        ],
        "bac_a_sable_codex": null,
        "connexions": {
          "claude": "jeton_reconnu",
          "codex": "compte_chatgpt",
          "plan_codex": "prolite"
        },
        "depots": [
          {
            "alias": "jetable"
          }
        ],
        "isolement_linux": {
          "bwrap": "refuse",
          "codex_sans_bac_a_sable": "refuse",
          "ecriture_admise": {
            "claude": true,
            "codex": false
          },
          "proc_neuf": false,
          "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
          "regime": "B",
          "reseau_coupe": false,
          "sonde_le": "2026-10-01T11:12:55Z",
          "uid_separes": true
        },
        "politique": {
          "alias_claude_permis": [
            "opus",
            "sonnet"
          ],
          "cartes_par_jour": 20,
          "concurrence": 1,
          "conditions": {
            "claude": "2026-10-01",
            "codex": "2026-10-01"
          },
          "duree_max_carte_s": 3600,
          "efforts_interdits": [
            "max",
            "ultra",
            "ultracode"
          ],
          "executants": [
            "codex",
            "claude"
          ],
          "modeles_codex_permis": [],
          "paliers_admis": [
            "default"
          ],
          "reseau_executants": false
        },
        "poste": {
          "compte": "uid_dedie",
          "hermes_meme_enveloppe_que_codex": true,
          "hote": "railway",
          "nom": "Exécutant Railway",
          "noyau": "6.12.10",
          "plateforme": "linux",
          "politique_empreinte": "5d1e0c7a9b42",
          "python": "3.12.10",
          "windows": null
        },
        "protocole": "acp-machine/1",
        "releve_le": "2026-10-01T11:12:55Z",
        "releves": {
          "poste-claude": 2,
          "poste-codex": 1
        },
        "version_poste": "1.0.0",
        "versions": {
          "claude": {
            "conforme": true,
            "lue": "2.1.283",
            "testee": "2.1.283"
          },
          "codex": {
            "conforme": true,
            "lue": "0.156.1",
            "testee": "0.156.1"
          }
        }
      },
      "alertes": [
        "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      ]
    },
    "alertes": [
      "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
    ],
    "ordres": [],
    "catalogue": {
      "etat": "connu",
      "voies": {
        "poste-codex": {
          "etat": "a_jour",
          "releve_id": 1,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 6,
          "perime": false,
          "source": "poste",
          "version_cli": "0.156.1",
          "modeles": [
            {
              "id": "factice-codex-1",
              "displayName": "Factice 1",
              "isDefault": true,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [
                "default",
                "priority"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-1",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            },
            {
              "id": "factice-codex-2",
              "displayName": "Factice 2",
              "isDefault": false,
              "supportedReasoningEfforts": [
                "low",
                "medium"
              ],
              "defaultReasoningEffort": "low",
              "serviceTiers": [
                "default"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-2",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            }
          ],
          "quotas": {
            "pourcentage_utilise": 41.0,
            "remise_a_zero": "2026-09-26T12:00:00Z"
          },
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "compte",
          "detail": null,
          "documentation_lue_le": null,
          "compteurs": [
            {
              "provider": "codex",
              "status": "ok",
              "source": "codex_app_server",
              "plan": "prolite",
              "limit_id": "codex",
              "windows": [
                {
                  "key": "primary",
                  "used_percent": 41,
                  "window_minutes": 300,
                  "resets_at": "2026-09-26T12:00:00Z"
                },
                {
                  "key": "secondary",
                  "used_percent": 12,
                  "window_minutes": 10080,
                  "resets_at": "2026-09-30T08:00:00Z"
                }
              ],
              "credits": null,
              "limit_reached": false,
              "reached_type": null,
              "observed_at": "2026-10-01T11:12:55Z",
              "detail": null
            }
          ],
          "badge": "releve_du_compte",
          "badge_libelle": "Relevé du compte"
        },
        "poste-claude": {
          "etat": "a_jour",
          "releve_id": 2,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 6,
          "perime": false,
          "source": "poste",
          "version_cli": "2.1.283",
          "modeles": [
            {
              "id": "opus",
              "displayName": "opus",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "opus[1m]",
              "displayName": "opus[1m]",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "haiku",
              "displayName": "haiku",
              "isDefault": null,
              "supportedReasoningEfforts": [],
              "defaultReasoningEffort": null,
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": null,
              "source_efforts": "documentation"
            }
          ],
          "quotas": null,
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "alias_documentes",
          "detail": null,
          "documentation_lue_le": "2026-09-26",
          "compteurs": [],
          "badge": "alias_documentes",
          "badge_libelle": "Alias documentés"
        }
      },
      "hermes": {
        "modele": "modèle par défaut du profil"
      },
      "routage": {
        "valide": false,
        "classes": {}
      },
      "politique": {
        "efforts_interdits": [
          "max",
          "ultra",
          "ultracode"
        ],
        "paliers_admis": [
          "default"
        ],
        "voies_par_classe": {
          "exploration": [
            "poste-claude",
            "poste-codex"
          ],
          "planification": [
            "hermes"
          ],
          "synthese": [
            "hermes"
          ],
          "repondre": [
            "hermes"
          ],
          "recherche_web": [
            "hermes"
          ],
          "architecture": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "implementation": [
            "poste-codex",
            "poste-claude"
          ],
          "debogage_tests": [
            "poste-codex",
            "poste-claude"
          ],
          "petite_tache": [
            "poste-codex",
            "poste-claude"
          ],
          "documentation": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "relecture": [
            "poste-codex",
            "poste-claude"
          ],
          "integration": [
            "poste-integration"
          ]
        }
      },
      "releve_factice": false
    },
    "executant": {
      "connu": true,
      "plateforme": "linux",
      "hote": "railway",
      "noyau": "6.12.10",
      "isolement": {
        "bwrap": "refuse",
        "codex_sans_bac_a_sable": "refuse",
        "ecriture_admise": {
          "claude": true,
          "codex": false
        },
        "proc_neuf": false,
        "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
        "regime": "B",
        "reseau_coupe": false,
        "sonde_le": "2026-10-01T11:12:55Z",
        "uid_separes": true
      },
      "bac_a_sable_codex": null,
      "conditions": {
        "claude": "2026-10-01",
        "codex": "2026-10-01"
      },
      "bornes": {
        "cartes_par_jour": 20,
        "duree_max_carte_s": 3600,
        "concurrence": 1
      },
      "peut_executer": true,
      "voies_disponibles": [
        "poste-claude",
        "poste-integration"
      ],
      "espace_libre_mio": 3120,
      "voies_fermees": {
        "poste-codex": "isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      },
      "cartes_en_attente_de_voie": [],
      "carte_en_cours": {
        "tableau": "acp-outil-jetable-478d",
        "carte": "t_26154e05",
        "run_id": 1,
        "connue": true,
        "projet": "p_5f53c3fba1f3",
        "projet_titre": "Outil jetable",
        "titre": "Exploration du dépôt « jetable »",
        "role": "exploration",
        "voie": "poste-claude",
        "modele_demande": "opus",
        "modele_servi": null,
        "effort": "low",
        "statut": "running",
        "dernier_battement": 1790853176,
        "a_nous": true
      },
      "branches_pretes": [],
      "revues": 0
    }
  },
  "routage_resolution": {
    "voies": {
      "poste-codex": {
        "etat": "a_jour",
        "releve_id": 1,
        "releve_le": 1790853175,
        "releve_le_lisible": "01/10/2026 13:12",
        "age_s": 7,
        "perime": false,
        "source": "poste",
        "version_cli": "0.156.1",
        "modeles": [
          {
            "id": "factice-codex-1",
            "displayName": "Factice 1",
            "isDefault": true,
            "supportedReasoningEfforts": [
              "low",
              "medium",
              "high"
            ],
            "defaultReasoningEffort": "medium",
            "serviceTiers": [
              "default",
              "priority"
            ],
            "defaultServiceTier": "default",
            "modele": "factice-codex-1",
            "cache": false,
            "remplace_par": null,
            "retrait_le": null,
            "nature": "catalogue_compte",
            "resolution_documentee": null,
            "source_efforts": "releve"
          },
          {
            "id": "factice-codex-2",
            "displayName": "Factice 2",
            "isDefault": false,
            "supportedReasoningEfforts": [
              "low",
              "medium"
            ],
            "defaultReasoningEffort": "low",
            "serviceTiers": [
              "default"
            ],
            "defaultServiceTier": "default",
            "modele": "factice-codex-2",
            "cache": false,
            "remplace_par": null,
            "retrait_le": null,
            "nature": "catalogue_compte",
            "resolution_documentee": null,
            "source_efforts": "releve"
          }
        ],
        "quotas": {
          "pourcentage_utilise": 41.0,
          "remise_a_zero": "2026-09-26T12:00:00Z"
        },
        "depots": [
          "jetable"
        ],
        "etat_releve": "ok",
        "origine_liste": "compte",
        "detail": null,
        "documentation_lue_le": null,
        "compteurs": [
          {
            "provider": "codex",
            "status": "ok",
            "source": "codex_app_server",
            "plan": "prolite",
            "limit_id": "codex",
            "windows": [
              {
                "key": "primary",
                "used_percent": 41,
                "window_minutes": 300,
                "resets_at": "2026-09-26T12:00:00Z"
              },
              {
                "key": "secondary",
                "used_percent": 12,
                "window_minutes": 10080,
                "resets_at": "2026-09-30T08:00:00Z"
              }
            ],
            "credits": null,
            "limit_reached": false,
            "reached_type": null,
            "observed_at": "2026-10-01T11:12:55Z",
            "detail": null
          }
        ],
        "badge": "releve_du_compte",
        "badge_libelle": "Relevé du compte"
      },
      "poste-claude": {
        "etat": "a_jour",
        "releve_id": 2,
        "releve_le": 1790853175,
        "releve_le_lisible": "01/10/2026 13:12",
        "age_s": 7,
        "perime": false,
        "source": "poste",
        "version_cli": "2.1.283",
        "modeles": [
          {
            "id": "opus",
            "displayName": "opus",
            "isDefault": null,
            "supportedReasoningEfforts": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "defaultReasoningEffort": "medium",
            "serviceTiers": [],
            "defaultServiceTier": null,
            "modele": null,
            "cache": false,
            "remplace_par": null,
            "retrait_le": null,
            "nature": "alias_documente",
            "resolution_documentee": "claude-opus-5-5",
            "source_efforts": "documentation"
          },
          {
            "id": "opus[1m]",
            "displayName": "opus[1m]",
            "isDefault": null,
            "supportedReasoningEfforts": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "defaultReasoningEffort": "medium",
            "serviceTiers": [],
            "defaultServiceTier": null,
            "modele": null,
            "cache": false,
            "remplace_par": null,
            "retrait_le": null,
            "nature": "alias_documente",
            "resolution_documentee": "claude-opus-5-5",
            "source_efforts": "documentation"
          },
          {
            "id": "haiku",
            "displayName": "haiku",
            "isDefault": null,
            "supportedReasoningEfforts": [],
            "defaultReasoningEffort": null,
            "serviceTiers": [],
            "defaultServiceTier": null,
            "modele": null,
            "cache": false,
            "remplace_par": null,
            "retrait_le": null,
            "nature": "alias_documente",
            "resolution_documentee": null,
            "source_efforts": "documentation"
          }
        ],
        "quotas": null,
        "depots": [
          "jetable"
        ],
        "etat_releve": "ok",
        "origine_liste": "alias_documentes",
        "detail": null,
        "documentation_lue_le": "2026-09-26",
        "compteurs": [],
        "badge": "alias_documentes",
        "badge_libelle": "Alias documentés"
      }
    },
    "releves": {
      "poste-codex": 1,
      "poste-claude": 2
    },
    "classes": {
      "exploration": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-claude",
          "poste-codex"
        ],
        "suggestion": {
          "entrees": [],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut.",
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
          ],
          "libelle": null
        }
      },
      "planification": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [],
          "libelle": null
        }
      },
      "synthese": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [],
          "libelle": null
        }
      },
      "repondre": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [],
          "libelle": null
        }
      },
      "recherche_web": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [],
          "libelle": null
        }
      },
      "architecture": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude",
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      },
      "implementation": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude"
        ],
        "suggestion": {
          "entrees": [],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      },
      "debogage_tests": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude"
        ],
        "suggestion": {
          "entrees": [],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      },
      "petite_tache": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude"
        ],
        "suggestion": {
          "entrees": [],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      },
      "documentation": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude",
          "hermes"
        ],
        "suggestion": {
          "entrees": [
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      },
      "relecture": {
        "etat": "non_validee",
        "entrees": [],
        "source": null,
        "valide_le": null,
        "valide_par": null,
        "voies": [
          "poste-codex",
          "poste-claude"
        ],
        "suggestion": {
          "entrees": [],
          "remarques": [
            "Refusé par ACP : la voie poste-codex est fermée sur l'exécutant : isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": null
        }
      }
    },
    "politique_hermes": {
      "efforts_interdits": [
        "max",
        "ultra",
        "ultracode"
      ],
      "paliers_admis": [
        "default"
      ],
      "efforts_hors_enveloppe": [
        "max",
        "ultra",
        "ultracode"
      ],
      "confirmation": "J'accepte une dépense hors enveloppe"
    },
    "politique_poste": {
      "alias_claude_permis": [
        "opus",
        "sonnet"
      ],
      "cartes_par_jour": 20,
      "concurrence": 1,
      "conditions": {
        "claude": "2026-10-01",
        "codex": "2026-10-01"
      },
      "duree_max_carte_s": 3600,
      "efforts_interdits": [
        "max",
        "ultra",
        "ultracode"
      ],
      "executants": [
        "codex",
        "claude"
      ],
      "modeles_codex_permis": [],
      "paliers_admis": [
        "default"
      ],
      "reseau_executants": false
    },
    "surcharges": [],
    "releve_factice": false,
    "resolutions_observees": [
      {
        "voie": "poste-claude",
        "alias": "opus",
        "modele_servi": "factice-servi-1",
        "observe_le": 1790853181,
        "observe_le_lisible": "01/10/2026 13:13"
      }
    ]
  },
  "questions_revue": {
    "questions": [],
    "triage": [],
    "bloquees": [],
    "tableaux_illisibles": [],
    "revues": [
      {
        "projet": "p_5f53c3fba1f3",
        "projet_titre": "Outil jetable",
        "tableau": "acp-outil-jetable-478d",
        "carte": "t_6f644e87",
        "titre": "Implémentation — e1 : Écrire",
        "role": "implementation",
        "voie": "poste-claude",
        "chemins": [
          ".github/workflows/ci.yml",
          "CLAUDE.md"
        ],
        "diffstat": {
          "ajouts": 12,
          "fichiers": 1,
          "retraits": 0
        },
        "branche": "hermes/t_6f644e87",
        "tete": "2222222222222222222222222222222222222222",
        "resume": "Ajout d'un contrôle de CI.",
        "diff": "Le diff reste sur l'exécutant (branche locale) : ACP n'en affiche aucun aperçu ; récupérez la branche pour le lire."
      }
    ]
  },
  "revue_acceptee": {
    "carte": "t_6f644e87",
    "etat": "done"
  },
  "poste_executant_branche": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790853182,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "machine": "m3b7783ebfe4",
      "message": null,
      "etat": "en_ligne",
      "derniere_vue": 1790853182,
      "derniere_vue_lisible": "01/10/2026 13:13",
      "hors_ligne_depuis": null,
      "source": "longpoll"
    },
    "machine": {
      "machine": {
        "id": "m3b7783ebfe4",
        "nom": "Exécutant Railway",
        "etat": "actif",
        "empreinte": "6CA2-C9E8",
        "protocole": "acp-machine/1",
        "version_poste": "1.0.0",
        "cree_le": 1790853175,
        "confirme_le": 1790853175,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790853182,
        "politique_valide": true,
        "plateforme": "linux",
        "hote": "railway"
      },
      "machines": {
        "a_confirmer": 0,
        "actif": 1,
        "revoque": 0
      },
      "codes_utilisables": 0
    },
    "inventaire": {
      "id": 1,
      "machine_id": "m3b7783ebfe4",
      "recu_le": 1790853175,
      "releve_le": 1790853175,
      "contenu": {
        "alertes": [
          "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
        ],
        "bac_a_sable_codex": null,
        "connexions": {
          "claude": "jeton_reconnu",
          "codex": "compte_chatgpt",
          "plan_codex": "prolite"
        },
        "depots": [
          {
            "alias": "jetable"
          }
        ],
        "isolement_linux": {
          "bwrap": "refuse",
          "codex_sans_bac_a_sable": "refuse",
          "ecriture_admise": {
            "claude": true,
            "codex": false
          },
          "proc_neuf": false,
          "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
          "regime": "B",
          "reseau_coupe": false,
          "sonde_le": "2026-10-01T11:12:55Z",
          "uid_separes": true
        },
        "politique": {
          "alias_claude_permis": [
            "opus",
            "sonnet"
          ],
          "cartes_par_jour": 20,
          "concurrence": 1,
          "conditions": {
            "claude": "2026-10-01",
            "codex": "2026-10-01"
          },
          "duree_max_carte_s": 3600,
          "efforts_interdits": [
            "max",
            "ultra",
            "ultracode"
          ],
          "executants": [
            "codex",
            "claude"
          ],
          "modeles_codex_permis": [],
          "paliers_admis": [
            "default"
          ],
          "reseau_executants": false
        },
        "poste": {
          "compte": "uid_dedie",
          "hermes_meme_enveloppe_que_codex": true,
          "hote": "railway",
          "nom": "Exécutant Railway",
          "noyau": "6.12.10",
          "plateforme": "linux",
          "politique_empreinte": "5d1e0c7a9b42",
          "python": "3.12.10",
          "windows": null
        },
        "protocole": "acp-machine/1",
        "releve_le": "2026-10-01T11:12:55Z",
        "releves": {
          "poste-claude": 2,
          "poste-codex": 1
        },
        "version_poste": "1.0.0",
        "versions": {
          "claude": {
            "conforme": true,
            "lue": "2.1.283",
            "testee": "2.1.283"
          },
          "codex": {
            "conforme": true,
            "lue": "0.156.1",
            "testee": "0.156.1"
          }
        }
      },
      "alertes": [
        "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      ]
    },
    "alertes": [
      "Écriture Codex non admise sur l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
    ],
    "ordres": [],
    "catalogue": {
      "etat": "connu",
      "voies": {
        "poste-codex": {
          "etat": "a_jour",
          "releve_id": 1,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 7,
          "perime": false,
          "source": "poste",
          "version_cli": "0.156.1",
          "modeles": [
            {
              "id": "factice-codex-1",
              "displayName": "Factice 1",
              "isDefault": true,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [
                "default",
                "priority"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-1",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            },
            {
              "id": "factice-codex-2",
              "displayName": "Factice 2",
              "isDefault": false,
              "supportedReasoningEfforts": [
                "low",
                "medium"
              ],
              "defaultReasoningEffort": "low",
              "serviceTiers": [
                "default"
              ],
              "defaultServiceTier": "default",
              "modele": "factice-codex-2",
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "catalogue_compte",
              "resolution_documentee": null,
              "source_efforts": "releve"
            }
          ],
          "quotas": {
            "pourcentage_utilise": 41.0,
            "remise_a_zero": "2026-09-26T12:00:00Z"
          },
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "compte",
          "detail": null,
          "documentation_lue_le": null,
          "compteurs": [
            {
              "provider": "codex",
              "status": "ok",
              "source": "codex_app_server",
              "plan": "prolite",
              "limit_id": "codex",
              "windows": [
                {
                  "key": "primary",
                  "used_percent": 41,
                  "window_minutes": 300,
                  "resets_at": "2026-09-26T12:00:00Z"
                },
                {
                  "key": "secondary",
                  "used_percent": 12,
                  "window_minutes": 10080,
                  "resets_at": "2026-09-30T08:00:00Z"
                }
              ],
              "credits": null,
              "limit_reached": false,
              "reached_type": null,
              "observed_at": "2026-10-01T11:12:55Z",
              "detail": null
            }
          ],
          "badge": "releve_du_compte",
          "badge_libelle": "Relevé du compte"
        },
        "poste-claude": {
          "etat": "a_jour",
          "releve_id": 2,
          "releve_le": 1790853175,
          "releve_le_lisible": "01/10/2026 13:12",
          "age_s": 7,
          "perime": false,
          "source": "poste",
          "version_cli": "2.1.283",
          "modeles": [
            {
              "id": "opus",
              "displayName": "opus",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "opus[1m]",
              "displayName": "opus[1m]",
              "isDefault": null,
              "supportedReasoningEfforts": [
                "low",
                "medium",
                "high",
                "xhigh",
                "max"
              ],
              "defaultReasoningEffort": "medium",
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": "claude-opus-5-5",
              "source_efforts": "documentation"
            },
            {
              "id": "haiku",
              "displayName": "haiku",
              "isDefault": null,
              "supportedReasoningEfforts": [],
              "defaultReasoningEffort": null,
              "serviceTiers": [],
              "defaultServiceTier": null,
              "modele": null,
              "cache": false,
              "remplace_par": null,
              "retrait_le": null,
              "nature": "alias_documente",
              "resolution_documentee": null,
              "source_efforts": "documentation"
            }
          ],
          "quotas": null,
          "depots": [
            "jetable"
          ],
          "etat_releve": "ok",
          "origine_liste": "alias_documentes",
          "detail": null,
          "documentation_lue_le": "2026-09-26",
          "compteurs": [],
          "badge": "alias_documentes",
          "badge_libelle": "Alias documentés"
        }
      },
      "hermes": {
        "modele": "modèle par défaut du profil"
      },
      "routage": {
        "valide": false,
        "classes": {}
      },
      "politique": {
        "efforts_interdits": [
          "max",
          "ultra",
          "ultracode"
        ],
        "paliers_admis": [
          "default"
        ],
        "voies_par_classe": {
          "exploration": [
            "poste-claude",
            "poste-codex"
          ],
          "planification": [
            "hermes"
          ],
          "synthese": [
            "hermes"
          ],
          "repondre": [
            "hermes"
          ],
          "recherche_web": [
            "hermes"
          ],
          "architecture": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "implementation": [
            "poste-codex",
            "poste-claude"
          ],
          "debogage_tests": [
            "poste-codex",
            "poste-claude"
          ],
          "petite_tache": [
            "poste-codex",
            "poste-claude"
          ],
          "documentation": [
            "poste-codex",
            "poste-claude",
            "hermes"
          ],
          "relecture": [
            "poste-codex",
            "poste-claude"
          ],
          "integration": [
            "poste-integration"
          ]
        }
      },
      "releve_factice": false
    },
    "executant": {
      "connu": true,
      "plateforme": "linux",
      "hote": "railway",
      "noyau": "6.12.10",
      "isolement": {
        "bwrap": "refuse",
        "codex_sans_bac_a_sable": "refuse",
        "ecriture_admise": {
          "claude": true,
          "codex": false
        },
        "proc_neuf": false,
        "raison": "Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture.",
        "regime": "B",
        "reseau_coupe": false,
        "sonde_le": "2026-10-01T11:12:55Z",
        "uid_separes": true
      },
      "bac_a_sable_codex": null,
      "conditions": {
        "claude": "2026-10-01",
        "codex": "2026-10-01"
      },
      "bornes": {
        "cartes_par_jour": 20,
        "duree_max_carte_s": 3600,
        "concurrence": 1
      },
      "peut_executer": true,
      "voies_disponibles": [
        "poste-integration"
      ],
      "espace_libre_mio": 3120,
      "voies_fermees": {
        "poste-codex": "isolement de l'exécutant (régime B) : Bac à sable Linux refusé par la plateforme (régime B) : voie Codex fermée en écriture."
      },
      "cartes_en_attente_de_voie": [],
      "carte_en_cours": null,
      "branches_pretes": [
        {
          "projet": "p_5f53c3fba1f3",
          "projet_titre": "Outil jetable",
          "depot": "jetable",
          "branche": "hermes/projet-outil-jetable-478d",
          "tete": "2222222222222222222222222222222222222222",
          "termine_le": 1790853182,
          "commande": "railway ssh -i <clé dédiée> --service executant -- acp-poste bundle jetable hermes/projet-outil-jetable-478d"
        }
      ],
      "revues": 0
    }
  }
} as const;
