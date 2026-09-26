# Composants tiers livrés dans l'image d'ACP

Ce fichier est copié dans l'image (`/opt/acp/THIRD_PARTY.md`). Il recense les fichiers d'auteurs tiers
recopiés dans ce dépôt et livrés par l'image d'ACP, avec leur provenance exacte et le texte intégral de
leur licence. La liste fait foi avec `hermes/catalogue/catalogue.lock.json`, que
`scripts/verifier_catalogue.py` compare à ce fichier.

## emilkowalski/skills

- Auteur : Emil Kowalski
- Dépôt : https://github.com/emilkowalski/skills
- Commit : `d16ebe60d09a5ba2afcb7054ede9d0a10c9f6128`
- Licence : MIT
- Livré sous : `/opt/acp/skills/emil-kowalski/` (`emil-design-eng`, `animation-vocabulary`, `apple-design`, `mobile-native`, `pick-ui-library`, `animate`, `ask-sonner`)

```text
MIT License

Copyright (c) 2026 Emil Kowalski

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## leonxlnx/taste-skill

- Auteur : Leonxlnx
- Dépôt : https://github.com/leonxlnx/taste-skill
- Commit : `c184364c58658b2f131b4ae8bd3d206cabb3deee`
- Licence : MIT
- Livré sous : `/opt/acp/skills/taste-skill/` (`design-taste-frontend`, `minimalist-ui`, `high-end-visual-design`)

```text
MIT License

Copyright (c) 2026 Leonxlnx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## affaan-m/ECC

- Auteur : Affaan Mustafa (et contributeurs du dépôt)
- Dépôt : https://github.com/affaan-m/ECC
- Commit : `5064474d4d762dc9640234a41617cccb79185cec` (étiquette `v2.2.1`)
- Licence : MIT
- Livré sous : `/opt/acp/skills/ecc/` (`security-review`, `accessibility`, `mle-workflow`, `python-patterns`)

```text
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## NousResearch/hermes-agent

- Auteur : Nous Research
- Dépôt : https://github.com/NousResearch/hermes-agent
- Commit : `f97608f178d1ffeca59860195ab7da295f7c8e5f` (étiquette `v2026.9.24`)
- Licence : MIT
- Livré sous : `/opt/acp/contrat/gateway-contract.openrpc.json` (copie du contrat JSON-RPC de la passerelle,
  voir `hermes/contrat/README.md`). L'image elle-même dérive de l'image officielle de Hermes Agent.

```text
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
