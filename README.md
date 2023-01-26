# Proxy cadastre.gouv
Proxy permettant à partir d'un seul point d'accès de disposer de l'intégralité des flux WMS (un par commune) depuis cadastre.gouv.fr...
Ce service s'utilise comme une sercice OGC de type WMS. exemple : (https://tiles.craig.fr/cadastre.gouv?SERVICE=WMS&REQUEST=GetCapabilities)
Il est recommandé d'utiliser une clé premium cadastre.gouv.fr : (https://www.cadastre.gouv.fr/scpc/afficherServiceWMS.do?CSRF_TOKEN=0QSM-EWVC-RJ2P-ETJA-FS83-ZWFS-GQES-BYMR)

## différences avec https://github.com/spelhate/proxycad
Ce proxy est très fortement inspiré par https://github.com/spelhate/proxycad, mais avec comme différences:
- réécrit en python/WSGI, s'intègre mieux avec l'infrastructure du CRAIG
- configuration dans un fichier à part
- support de l'interrogation des couches `CP.CadastralParcel` et `BU.Building` via l'opération `GetFeatureInfo`
- possibilité d'utiliser n'importe quelle source de donnée GDAL/OGR pour la couche d'intersection des communes

## Prérequis
Disposer d'une couche spatiale des communes de la zone souhaitée (une région,
la france..) disposant à minima d'un champ avec le code INSEE.

la couche ADMINEXPRESS COG CARTO (https://geoservices.ign.fr/adminexpress) est
un bon exemple, mais on peut aussi utiliser les communes d'openstreetmap comme
le fait par défaut https://github.com/spelhate/proxycad

## Paramétrage
### Editer la configuration
- clé premium,
- chemin du fichier contenant la couche (ou chaine de connection postgis)
- nom de la couche communale
- nom du champ insee

### Editer le fichier getcap.xml.j2
- Modifier les titres/résumés si besoin
- Les urls/emprises sont calculées automatiquement depuis l'environnement/couche support

## Déploiement
- installer les librairies python gdal, flask, request et PIL/pillow. (debian: `python3-gdal`, `python3-flask`, `python3-requests`, `python3-pil`)
- installer un middleware WSGI comme gunicorn, une fois cloné ce repository dans `/srv/cadastre.gouv` cette configuration pour supervisord
  (a mettre dans `/etc/supervisord/conf.d/proxycad.conf`) fonctionne:
```
[program:proxycad]
command=/usr/bin/gunicorn --name=proxycad --workers=2 --bind=unix:/var/run/proxycad.sock --pid=/var/run/proxycad.pid proxycad:app
directory=/srv/cadastre.gouv
stdout_logfile=/var/log/supervisor/%(program_name)s.out
redirect_stderr=true
```
- bout de config pour nginx en frontal:
```
location /cadastre.gouv {
	add_header "Access-Control-Allow-Origin" "*";
	proxy_pass http://unix:/var/run/proxycad.sock;
}
```
- le service peut aussi être démarré avec `FLASK_APP=proxycad flask run` et reverse-proxyfié par nginx sur http://localhost:5000

## Utilisation

Exemple d'utilisation : (http://geobretagne.fr/mapfishapp/map/b391ec0966a3ff4da4c78bcfbc5688bf)
