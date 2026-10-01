// Réponses RÉELLES des routes du propriétaire de l'étape P5 (greffon acp-poste), capturées dans l'image de test
// construite depuis le commit 39ad0cd (routeur du greffon, couture par jeton de Hermes, session factice, HERMES_HOME
// jetable) : poste non configuré, à confirmer, en ligne après l'inventaire de l'exemple partagé
// (hermes/tests/outils/fixtures_machine/inventaire_requete.json), routage, refus d'une table, quotas, relevé Codex
// identique au catalogue embarqué. Seul le code d'enrôlement est remplacé par une valeur factice (le vrai n'est
// jamais gardé). Rien d'autre n'est modifié à la main.
export const FORMES = {
  "poste_non_configure": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": null,
      "etat": "non_configure",
      "machine": null,
      "message": "Le poste n'a jamais été vu : enrôlez-le depuis la page Poste.",
      "derniere_vue": null,
      "hors_ligne_depuis": null
    },
    "machine": {
      "machine": null,
      "machines": {
        "a_confirmer": 0,
        "actif": 0,
        "revoque": 0
      },
      "codes_utilisables": 0
    },
    "inventaire": null,
    "alertes": [],
    "ordres": [],
    "catalogue": {
      "etat": "inconnu",
      "voies": {
        "poste-codex": {
          "etat": "inconnu",
          "releve_le": null,
          "badge": "inconnu",
          "badge_libelle": "Inconnu"
        },
        "poste-claude": {
          "etat": "inconnu",
          "releve_le": null,
          "badge": "inconnu",
          "badge_libelle": "Inconnu"
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
          "integration": []
        }
      },
      "releve_factice": false,
      "message": "Catalogue du poste inconnu : aucun relevé (le poste publie son inventaire une fois enrôlé et confirmé)."
    }
  },
  "routage_vide": {
    "voies": {
      "poste-codex": {
        "etat": "inconnu",
        "releve_le": null,
        "badge": "inconnu",
        "badge_libelle": "Inconnu"
      },
      "poste-claude": {
        "etat": "inconnu",
        "releve_le": null,
        "badge": "inconnu",
        "badge_libelle": "Inconnu"
      }
    },
    "releves": {
      "poste-codex": null,
      "poste-claude": null
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
          "remarques": [],
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
          "remarques": [],
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
          "remarques": [],
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
          "remarques": [],
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
          "remarques": [],
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
          "remarques": [],
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
          "remarques": [],
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
    "politique_poste": null,
    "surcharges": [],
    "releve_factice": false
  },
  "quotas_vides": {
    "poste-codex": {
      "etat": "inconnu",
      "releve_le": null,
      "compteurs": [],
      "seuil_pct": 90,
      "source": "codex_app_server"
    },
    "poste-claude": {
      "etat": "inconnu",
      "releve_le": null,
      "compteurs": [],
      "seuil_pct": 90,
      "source": "ligne_etat_sessions_proprietaire",
      "source_libelle": "Ligne d'état de vos sessions Claude Code sur ce PC (même abonnement déclaré)"
    },
    "hermes": {
      "etat": "inconnu",
      "libelle": "Inconnu"
    }
  },
  "code": {
    "code": "acpe_CODE-DE-TEST",
    "expire_le": 1790452215,
    "validite_s": 600,
    "protocole": "acp-machine/1",
    "commande": "& \"$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd\" enroler"
  },
  "poste_a_confirmer": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": {
        "id": "m1563c2ef174",
        "nom": "Poste Windows",
        "etat": "a_confirmer",
        "empreinte": "6093-5536",
        "protocole": "acp-machine/1",
        "version_poste": "0.11.0",
        "cree_le": 1790451615,
        "confirme_le": null,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": null,
        "politique_valide": true
      },
      "etat": "a_confirmer",
      "machine": "m1563c2ef174",
      "derniere_vue": null,
      "hors_ligne_depuis": null,
      "message": "Poste enrôlé, en attente de la confirmation de son empreinte 6093-5536 sur la page Poste."
    },
    "machine": {
      "machine": {
        "id": "m1563c2ef174",
        "nom": "Poste Windows",
        "etat": "a_confirmer",
        "empreinte": "6093-5536",
        "protocole": "acp-machine/1",
        "version_poste": "0.11.0",
        "cree_le": 1790451615,
        "confirme_le": null,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": null,
        "politique_valide": true
      },
      "machines": {
        "a_confirmer": 1,
        "actif": 0,
        "revoque": 0
      },
      "codes_utilisables": 0
    },
    "inventaire": null,
    "alertes": [],
    "ordres": [],
    "catalogue": {
      "etat": "inconnu",
      "voies": {
        "poste-codex": {
          "etat": "inconnu",
          "releve_le": null,
          "badge": "inconnu",
          "badge_libelle": "Inconnu"
        },
        "poste-claude": {
          "etat": "inconnu",
          "releve_le": null,
          "badge": "inconnu",
          "badge_libelle": "Inconnu"
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
          "integration": []
        }
      },
      "releve_factice": false,
      "message": "Catalogue du poste inconnu : aucun relevé (le poste publie son inventaire une fois enrôlé et confirmé)."
    }
  },
  "refus_empreinte": {
    "detail": {
      "code": "empreinte_differente",
      "message": "L'empreinte saisie ne correspond pas à celle du poste enrôlé : n'activez pas ce poste ; révoquez-le et recommencez."
    }
  },
  "poste_en_ligne": {
    "poste": {
      "pause_reclamations": false,
      "cartes_en_attente": 0,
      "poste": {
        "id": "m1563c2ef174",
        "nom": "Poste Windows",
        "etat": "actif",
        "empreinte": "6093-5536",
        "protocole": "acp-machine/1",
        "version_poste": "0.11.0",
        "cree_le": 1790451615,
        "confirme_le": 1790451615,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790451615,
        "politique_valide": true
      },
      "machine": "m1563c2ef174",
      "message": null,
      "etat": "en_ligne",
      "derniere_vue": 1790451615,
      "derniere_vue_lisible": "26/09/2026 21:40",
      "hors_ligne_depuis": null,
      "source": "longpoll"
    },
    "machine": {
      "machine": {
        "id": "m1563c2ef174",
        "nom": "Poste Windows",
        "etat": "actif",
        "empreinte": "6093-5536",
        "protocole": "acp-machine/1",
        "version_poste": "0.11.0",
        "cree_le": 1790451615,
        "confirme_le": 1790451615,
        "revoque_le": null,
        "motif_revocation": null,
        "derniere_requete": 1790451615,
        "politique_valide": true
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
      "machine_id": "m1563c2ef174",
      "recu_le": 1790451620,
      "releve_le": 1790451620,
      "contenu": {
        "alertes": [],
        "bac_a_sable_codex": {
          "ecriture_admise": true,
          "lu_le": "2026-09-26T19:40:20Z",
          "mode_lu": "elevated",
          "origine_mode": "sessionFlags",
          "palier_lu": "default",
          "raison": null,
          "readiness": "ready",
          "stockage_identifiants_lu": "keyring"
        },
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
        "politique": {
          "alias_claude_permis": [
            "opus",
            "opus[1m]",
            "sonnet",
            "haiku"
          ],
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
          "compte": "dedie",
          "hermes_meme_enveloppe_que_codex": false,
          "nom": "Poste Windows",
          "politique_empreinte": "9c2e41ab07d3",
          "python": "3.12.10",
          "windows": "10.0.19045"
        },
        "protocole": "acp-machine/1",
        "releve_le": "2026-09-26T19:40:20Z",
        "releves": {
          "poste-claude": 2,
          "poste-codex": 1
        },
        "version_poste": "0.11.0",
        "versions": {
          "claude": {
            "conforme": true,
            "lue": "2.1.280",
            "testee": "2.1.280"
          },
          "codex": {
            "conforme": true,
            "lue": "0.156.1",
            "testee": "0.156.1"
          }
        }
      },
      "alertes": []
    },
    "alertes": [],
    "ordres": [],
    "catalogue": {
      "etat": "connu",
      "voies": {
        "poste-codex": {
          "etat": "a_jour",
          "releve_id": 1,
          "releve_le": 1790451620,
          "releve_le_lisible": "26/09/2026 21:40",
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
              "observed_at": "2026-09-26T19:40:20Z",
              "detail": null
            }
          ],
          "badge": "releve_du_compte",
          "badge_libelle": "Relevé du compte"
        },
        "poste-claude": {
          "etat": "a_jour",
          "releve_id": 2,
          "releve_le": 1790451620,
          "releve_le_lisible": "26/09/2026 21:40",
          "age_s": 0,
          "perime": false,
          "source": "poste",
          "version_cli": "2.1.280",
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
          "integration": []
        }
      },
      "releve_factice": false
    }
  },
  "releve_demande": {
    "ordre": 1,
    "en_attente_du_poste": false,
    "message": "Ordre de relevé mis en file : le poste le reçoit à sa prochaine attente."
  },
  "routage": {
    "voies": {
      "poste-codex": {
        "etat": "a_jour",
        "releve_id": 1,
        "releve_le": 1790451620,
        "releve_le_lisible": "26/09/2026 21:40",
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
            "observed_at": "2026-09-26T19:40:20Z",
            "detail": null
          }
        ],
        "badge": "releve_du_compte",
        "badge_libelle": "Relevé du compte"
      },
      "poste-claude": {
        "etat": "a_jour",
        "releve_id": 2,
        "releve_le": 1790451620,
        "releve_le_lisible": "26/09/2026 21:40",
        "age_s": 0,
        "perime": false,
        "source": "poste",
        "version_cli": "2.1.280",
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
          "entrees": [
            {
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            },
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
          "entrees": [
            {
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
          "entrees": [
            {
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
          "entrees": [
            {
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            },
            {
              "voie": "hermes",
              "modele": null,
              "effort": null,
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
          "entrees": [
            {
              "voie": "poste-codex",
              "modele": "factice-codex-1",
              "effort": "medium",
              "palier": "default"
            }
          ],
          "remarques": [
            "Aucune suggestion : le relevé Claude ne désigne pas de modèle par défaut."
          ],
          "libelle": "Suggestion calculée depuis le relevé du 26/09/2026 21:40."
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
        "opus[1m]",
        "sonnet",
        "haiku"
      ],
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
    "releve_factice": false
  },
  "refus_table": {
    "detail": {
      "code": "table_refusee",
      "message": "Table de routage refusée : 1 entrée(s) refusée(s) ; rien n'a été enregistré.",
      "refus": [
        {
          "classe": "implementation",
          "rang": 0,
          "code": "modele_absent",
          "message": "Refusé par ACP : le modèle « inexistant » ne figure pas dans le relevé de la voie poste-codex (relevé du 26/09/2026 21:40)."
        }
      ]
    }
  },
  "quotas": {
    "poste-codex": {
      "etat": "releve",
      "releve_le": 1790451620,
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
              "resets_at": "2026-09-26T12:00:00Z",
              "remaining_percent": 59
            },
            {
              "key": "secondary",
              "used_percent": 12,
              "window_minutes": 10080,
              "resets_at": "2026-09-30T08:00:00Z",
              "remaining_percent": 88
            }
          ],
          "credits": null,
          "limit_reached": false,
          "reached_type": null,
          "observed_at": "2026-09-26T19:40:20Z",
          "detail": null,
          "worker_id": "m1563c2ef174",
          "worker_name": "Poste Windows",
          "received_at": "2026-09-26T19:40:20Z",
          "stale": false
        }
      ],
      "seuil_pct": 90,
      "source": "codex_app_server",
      "releve_le_lisible": "26/09/2026 21:40",
      "releve_id": 1,
      "etat_releve": "ok",
      "detail": null,
      "source_releve": "poste",
      "resume": {
        "pourcentage_utilise": 41.0,
        "remise_a_zero": "2026-09-26T12:00:00Z"
      }
    },
    "poste-claude": {
      "etat": "releve",
      "releve_le": 1790451620,
      "compteurs": [],
      "seuil_pct": 90,
      "source": "ligne_etat_sessions_proprietaire",
      "source_libelle": "Ligne d'état de vos sessions Claude Code sur ce PC (même abonnement déclaré)",
      "releve_le_lisible": "26/09/2026 21:40",
      "releve_id": 2,
      "etat_releve": "ok",
      "detail": null,
      "source_releve": "poste",
      "resume": null
    },
    "hermes": {
      "etat": "inconnu",
      "libelle": "Inconnu"
    }
  },
  "routage_secours": {
    "voies": {
      "poste-codex": {
        "etat": "a_jour",
        "releve_id": 3,
        "releve_le": 1790451620,
        "releve_le_lisible": "26/09/2026 21:40",
        "age_s": 120,
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
        "origine_liste": "identique_au_catalogue_embarque",
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
            "observed_at": "2026-09-26T19:40:20Z",
            "detail": null
          }
        ],
        "badge": "liste_de_secours_probable",
        "badge_libelle": "Liste de secours probable"
      },
      "poste-claude": {
        "etat": "a_jour",
        "releve_id": 4,
        "releve_le": 1790451620,
        "releve_le_lisible": "26/09/2026 21:40",
        "age_s": 120,
        "perime": false,
        "source": "poste",
        "version_cli": "2.1.280",
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
      "poste-codex": 3,
      "poste-claude": 4
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage."
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
            "Refusé par ACP : le relevé Codex du 26/09/2026 21:40 est une liste de secours (identique au catalogue embarqué de Codex 0.156.1), pas celle de votre compte. Reconnectez Codex, ou acceptez ce relevé depuis la page Routage.",
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
        "opus[1m]",
        "sonnet",
        "haiku"
      ],
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
    "releve_factice": false
  }
} as const;
