// sw.js — hors ligne (#276, P5) : la page s'ouvre aussi sans réseau.
//
// Les réponses, elles, sont déjà gardées dans le navigateur après chaque carte
// et envoyées à Firestore au retour du réseau (scheduleSync sur « online ») :
// il ne manquait que de pouvoir ouvrir la page. Ici :
//  - la page, les paquets (.json) et le SDK Firebase : le réseau d'abord (la
//    dernière version quand il y en a), la copie gardée quand il n'y en a pas ;
//  - les sons et les images : la copie gardée d'abord (ils ne changent pas),
//    au plus MEDIA_MAX, les plus anciens sortent ;
//  - Firestore et le reste de Google : jamais touchés (la synchro reste celle de l'app).
var PAGES = "typeinanki-pages-v1", MEDIA = "typeinanki-media-v1", MEDIA_MAX = 3000;

self.addEventListener("install", function (e) { self.skipWaiting(); });
self.addEventListener("activate", function (e) {
    e.waitUntil(caches.keys().then(function (ks) {
        return Promise.all(ks.filter(function (k) { return k !== PAGES && k !== MEDIA; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); }));
});

function networkFirst(req) {
    return fetch(req).then(function (res) {
        if (res && (res.ok || res.type === "opaque")) {
            var copy = res.clone();
            caches.open(PAGES).then(function (c) { c.put(req, copy); });
        }
        return res;
    }).catch(function () {
        return caches.match(req, { ignoreSearch: req.mode === "navigate" }).then(function (r) {
            if (r || req.mode !== "navigate") return r || Response.error();
            return caches.match("./", { ignoreSearch: true }).then(function (home) { return home || Response.error(); });
        });
    });
}

function url(req) { return new URL(req.url); }

function cacheFirst(req) {
    return caches.match(req.url).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (res) {
            // a sound asked by range (206) can't be stored as is: the whole file, fetched once more behind
            if (res && res.status === 206 && url(req).origin === self.location.origin)
                fetch(req.url).then(function (full) { if (full.status === 200) caches.open(MEDIA).then(function (c) { c.put(req.url, full); }); }).catch(function () {});
            if (res && (res.status === 200 || res.type === "opaque")) {
                var copy = res.clone();
                caches.open(MEDIA).then(function (c) {
                    c.put(req, copy).then(function () {
                        return c.keys();
                    }).then(function (ks) {
                        if (ks.length > MEDIA_MAX) return Promise.all(ks.slice(0, ks.length - MEDIA_MAX).map(function (k) { return c.delete(k); }));
                    });
                });
            }
            return res;
        });
    });
}

self.addEventListener("fetch", function (e) {
    var req = e.request;
    if (req.method !== "GET") return;
    var url = new URL(req.url);
    if (/googleapis\.com$|firebaseio\.com$|google\.com$/.test(url.hostname)) return; // Firestore, sign-in: as they are
    var media = req.destination === "audio" || req.destination === "image" || req.destination === "video"
        || /\.(mp3|ogg|wav|m4a|png|jpe?g|gif|webp|svg)$/i.test(url.pathname);
    if (media) { e.respondWith(cacheFirst(req)); return; }
    var mine = url.origin === self.location.origin;
    if (req.mode === "navigate" || (mine && /\.(json|html|js|css)$/i.test(url.pathname)) || url.hostname === "www.gstatic.com")
        e.respondWith(networkFirst(req));
});
