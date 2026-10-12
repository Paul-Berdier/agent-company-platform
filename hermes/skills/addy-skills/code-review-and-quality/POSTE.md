# Relecture du code et de ses risques

Adaptation ACP de addyosmani/agent-skills, commit a06bc63b3f8b829c14b0bbf53d99fefc39d58092 (MIT). Texte intégral et références conservés dans le catalogue ; cette application est une synthèse française ciblée, pas la totalité du texte amont.

Relisez le diff, ses appelants et les tests dans leur contexte. Cherchez d’abord les défauts de comportement, de sécurité, d’intégrité des données et de performance réellement déclenchables. Rapportez chaque défaut avec fichier, ligne, scénario et conséquence ; séparez faits et hypothèses. Vérifiez les validations aux frontières et la gestion des erreurs. Ne modifiez aucun fichier pendant la relecture et ne présentez jamais un test non exécuté comme réussi.
