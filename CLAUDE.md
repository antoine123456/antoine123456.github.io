# espanol-trainer

Le fichier d'idées `idee.md` est affiché par kanban-terminal (`kanban`, Gantt avec G) :

@~/Documents/kanban-terminal/docs/pour-claude.md

## Aperçus (captures d'écran)

Par défaut, les aperçus téléphone se font avec `apercu.js` : iPhone 14 sous Safari (iOS 26), en portrait (écran 390 × 844, page 390 × 736 sous la barre d'état et au-dessus de la barre d'adresse compacte) et en paysage (844 × 390) quand la mise en page change, en thème clair et en thème sombre. `shot()` encadre la capture avec la barre d'état, la barre d'adresse et la barre d'accueil, comme une capture faite sur le téléphone. La fenêtre des nouveautés est fermée d'office. Chromium remplace WebKit et les polices Linux remplacent SF Pro : tailles et mise en page sont celles de l'iPhone, le dessin des lettres et des emoji diffère un peu.

```js
const { phone, shot } = require('./apercu.js');
const { page, close } = await phone({ landscape: false, dark: true });
await page.waitForTimeout(6000);          // les paquets se chargent
// … piloter l'appli (openBrowse, startStudy…) …
await shot(page, 'apercu.png');
await close();
```
