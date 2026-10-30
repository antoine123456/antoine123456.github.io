# Branche firebase-debug

`index.html` est une page de diagnostic : l'état de la connexion à Firestore, un choix de nom d'utilisateur (sans Google, sans mot de passe) et un petit explorateur de la base. L'appli elle-même est dans `app.html`.

## Règles Firestore de test

Sans authentification, Firestore refuse tout (`permission-denied`). Pour tester, dans la console Firebase → Firestore → Rules :

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if true;
    }
  }
}
```

⚠️ Pour les tests seulement : n'importe qui connaissant le projet peut lire et écrire `users/…`. Avant d'ouvrir l'appli à d'autres personnes, il faudra une vraie authentification (#9).

## Voir les données

- Dans la page : section « Explorateur » (la collection `users`, le document choisi et sa sous-collection `sources`).
- Explorateur complet, comme MongoDB Compass : https://console.firebase.google.com/project/type-in-anki/firestore/data
