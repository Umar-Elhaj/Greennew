# Glossaire FR ⇄ EN — GREEN

Référence pour toute nouvelle chaîne (`frontend/i18n/*.json`, `backend/i18n.py`, `diseases.json`).
Le français vouvoie l'utilisateur. Les clés sont hiérarchisées par page puis composant
(`map.grid.cell_size`, `common.actions.save`) ; toute chaîne visible passe par `I18n.t()` ou un attribut `data-i18n*`.

## Règles

- Une prédiction du modèle est une **maladie probable** (*probable disease*), jamais un diagnostic.
  Toute fiche affiche la mention « Prédiction de l'IA, pas un diagnostic ».
- Le « niveau d'alerte » (*alert level*) est dérivé de la **confiance du modèle**, pas de l'étendue des dégâts ;
  il vaut « Aucun » pour une plante saine. Ne jamais l'appeler « gravité » dans l'interface.
- Montants : `I18n.money()` (XAF ; affiché « FCFA » en `fr-CM`). Nombres et dates : `I18n.number()`, `I18n.date()`.
- Régions : valeur stockée = nom officiel français (`Extrême-Nord`), libellé traduit (`common.regions.*`).
- Pas de majuscule de titre en français (« Analyse caméra », pas « Analyse Caméra »).

## Termes

| Français | English | Remarque |
|---|---|---|
| exploitant, exploitation | farmer, farm | « agribusiness » évité |
| parcelle | parcel | pas « champ » dans l'interface |
| culture | crop | |
| maïs | maize | « corn » seulement dans les codes de classes du modèle |
| manioc | cassava | |
| tomate | tomato | |
| arachide | groundnut | pas « peanut » |
| plantain | plantain | |
| analyse | analysis | une image analysée = une analyse |
| fiche terrain | field sheet | |
| maladie probable | probable disease | |
| ravageur | pest | |
| confiance du modèle | model confidence | |
| niveau d'alerte | alert level | voir règles |
| sain / plante saine | healthy / healthy plant | |
| symptômes | symptoms | |
| actions recommandées | recommended actions | |
| produit homologué | approved product | |
| équipement de protection | protective equipment | |
| quadrillage, cellule | grid, cell | GREEN Map |
| parcours (du rover) | path, route | serpentin = *serpentine (boustrophedon)* |
| mission | mission | |
| point de passage | waypoint | |
| carte de chaleur | heatmap | choroplèthe par cellule |
| file d'envoi, en attente d'envoi | upload queue, waiting to be sent | caméra hors ligne |
| hors ligne / en ligne | offline / online | |
| consentement | consent | |
| partenaire | partner | rôle GREEN Data |
| agronome | agronomist | rôle |
| mildiou | late blight (tomate, pomme de terre) / downy mildew | selon l'agent pathogène |
| oïdium | powdery mildew | |
| alternariose | early blight | |
| cercosporiose noire | black Sigatoka | |
| mosaïque du manioc | cassava mosaic disease | |
| striure du maïs / rayure du maïs | maize streak / maize stripe | deux virus distincts |
| helminthosporiose du maïs | northern corn leaf blight | |
| chenille légionnaire d'automne | fall armyworm | |
| pourriture brune des cabosses | black pod | cacaoyer |
